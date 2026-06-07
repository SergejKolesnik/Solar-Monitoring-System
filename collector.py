import pandas as pd
import requests
import os
import imaplib
import email
import io
import json
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from sklearn.ensemble import RandomForestRegressor

SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
NUMERIC_COLS = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb', 'Fact_MW', 'Capacity_MW']
FEATURE_COLS = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb', 'Capacity_MW']

def get_sheet():
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS не знайдено")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID).sheet1

def load_df_from_sheet(sheet):
    data = sheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
    if not data:
        return pd.DataFrame(columns=['Time'] + NUMERIC_COLS)
    df = pd.DataFrame(data)
    # Видаляємо застарілий стовпець AI_MW якщо він ще є в таблиці
    df = df.drop(columns=['AI_MW'], errors='ignore')
    df['Time'] = pd.to_datetime(df['Time'])
    all_cols = NUMERIC_COLS + ['AI_Forecast_MW']
    for col in all_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '.').str.strip(),
                errors='coerce'
            ).fillna(0)
    return df

def save_df_to_sheet(sheet, df):
    save_cols = NUMERIC_COLS + (['AI_Forecast_MW'] if 'AI_Forecast_MW' in df.columns else [])
    # Гарантуємо що AI_MW не потрапить у збережені дані
    df = df.drop(columns=['AI_MW'], errors='ignore')
    df = df.sort_values('Time').drop_duplicates('Time').copy()
    for col in save_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).round(3)
    df['Time'] = df['Time'].astype(str)

    rows = []
    for _, row in df.iterrows():
        r = []
        for col in df.columns:
            if col == 'Time':
                r.append(str(row[col]))
            elif col in save_cols:
                r.append(float(row[col]))
            else:
                r.append(row[col] if row[col] != '' else 0)
        rows.append(r)

    header = [df.columns.tolist()]
    BATCH_SIZE = 500
    import time as _t

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            sheet.clear()
            sheet.update('A1', header)
            for start in range(0, len(rows), BATCH_SIZE):
                batch = rows[start:start + BATCH_SIZE]
                row_num = start + 2
                sheet.update(f'A{row_num}', batch)
                if start + BATCH_SIZE < len(rows):
                    _t.sleep(1)
            print(f"Google Sheet оновлено. Рядків: {len(df)}")
            return
        except Exception as e:
            print(f"Спроба {attempt}/{max_attempts} не вдалась: {e}")
            if attempt < max_attempts:
                _t.sleep(5)
    print("Не вдалось зберегти після 3 спроб")
def train_model(df):
    """Навчає модель на ВСІХ даних де є Fact_MW (включно з нічними нулями)."""
    features = [c for c in FEATURE_COLS if c in df.columns]
    df_train = df[df['Fact_MW'].notna()].copy()
    df_train = df_train.dropna(subset=features)
    if len(df_train) < 20:
        return None, features
    X = df_train[features].fillna(0).astype(float)
    y = df_train['Fact_MW'].astype(float)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    print(f"Модель навчена на {len(df_train)} записах (включно з нічними нулями)")
    return model, features

def save_ai_forecast(df, model, features):
    """
    Оновлює AI_Forecast_MW на сьогодні + 3 дні вперед.
    Завжди перезаписує. Нічні години (до 5:00 та після 21:00) = 0.
    """
    if model is None:
        print("Модель не навчена — пропускаємо прогноз ШІ")
        return df

    today = datetime.now().date()
    forecast_end = today + timedelta(days=3)
    mask_future = (
        (pd.to_datetime(df['Time']).dt.date >= today) &
        (pd.to_datetime(df['Time']).dt.date <= forecast_end)
    )

    if 'AI_Forecast_MW' not in df.columns:
        df['AI_Forecast_MW'] = 0.0

    df_to_predict = df[mask_future].copy()

    if df_to_predict.empty:
        print("Немає погодних даних для прогнозу")
        return df

    avail_features = [f for f in features if f in df_to_predict.columns]
    X_pred = df_to_predict[avail_features].fillna(0).astype(float)
    preds = model.predict(X_pred)

    hours = pd.to_datetime(df_to_predict['Time']).dt.hour
    preds = [round(float(p), 3) if 5 <= h <= 21 else 0.0 for p, h in zip(preds, hours)]

    df.loc[mask_future, 'AI_Forecast_MW'] = preds

    days_count = pd.to_datetime(df_to_predict['Time']).dt.date.nunique()
    non_zero = sum(1 for p in preds if p > 0)
    max_p = max(preds) if preds else 0
    print(f"AI_Forecast_MW оновлено: {days_count} дн., {non_zero} год. з генерацією, макс {max_p:.3f} МВт")
    return df

def parse_kwh_value(val_raw):
    if val_raw is None:
        return None
    val_str = (
        str(val_raw)
        .replace('\xa0', '')
        .replace(' ', '')
        .replace(',', '.')
        .strip()
    )
    if not val_str or val_str.lower() in ('nan', 'none', ''):
        return None
    f_val = pd.to_numeric(val_str, errors='coerce')
    if pd.isna(f_val):
        return None
    return round(f_val / 1000, 3)

def read_facts_from_email(days=30):
    facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))

        ids = []
        for folder in ['INBOX', '"[Gmail]/All Mail"']:
            try:
                status, _ = mail.select(folder)
                if status != 'OK':
                    continue
                date_from = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
                status2, data = mail.search(None, f'(SINCE "{date_from}")')
                if status2 == 'OK' and data and data[0]:
                    found = data[0].split()
                    if found:
                        ids = found
                        print(f"Знайдено {len(ids)} листів у {folder}")
                        break
            except Exception as fe:
                print(f"Папка: {fe}")
                continue

        if not ids:
            print("Листів не знайдено")
            mail.logout()
            return facts

        for num in reversed(ids):
            try:
                _, msg_data = mail.fetch(num, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                for part in msg.walk():
                    filename = part.get_filename()
                    if not filename or '.xls' not in filename.lower():
                        continue
                    try:
                        raw_data = part.get_payload(decode=True)
                        if not raw_data:
                            continue
                        excel_df = pd.read_excel(io.BytesIO(raw_data), header=None)
                        print(f"{filename}")
                        for i in range(2, len(excel_df)):
                            try:
                                t_raw = excel_df.iloc[i, 0]
                                if t_raw is None or str(t_raw).strip() in ('', 'nan'):
                                    continue
                                t = pd.to_datetime(t_raw, errors='coerce')
                                if pd.isna(t):
                                    continue
                                final_v = parse_kwh_value(excel_df.iloc[i, 5])
                                if final_v is None:
                                    continue
                                facts.append({
                                    'Time': t.to_pydatetime().replace(minute=0, second=0, microsecond=0),
                                    'Fact_MW': final_v
                                })
                            except Exception:
                                continue
                    except Exception as fe:
                        print(f"{filename}: {fe}")
            except Exception:
                continue

        mail.logout()
    except Exception as e:
        print(f"Пошта: {e}")
    return facts

def main():
    now = datetime.now()
    print(f"СТАРТ: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    sheet = get_sheet()
    df = load_df_from_sheet(sheet)
    print(f"Завантажено: {len(df)} рядків")

    # Читаємо факти з пошти
    facts = read_facts_from_email(days=30)
    if facts:
        df_new = pd.DataFrame(facts)
        df_new = df_new.groupby('Time')['Fact_MW'].max().reset_index()
        df = df.set_index('Time')
        df_new = df_new.set_index('Time')
        df.update(df_new)
        df = pd.concat([df, df_new[~df_new.index.isin(df.index)]]).reset_index()
        print(f"Фактів: {len(df_new)}, діапазон: {df_new['Fact_MW'].min():.3f}..{df_new['Fact_MW'].max():.3f} МВт")
    else:
        print("Нових фактів не знайдено")

    # Оновлення погоди
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        url = (
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
            f"47.631494,34.348690/"
            f"{(now-timedelta(days=7)).strftime('%Y-%m-%d')}/"
            f"{(now+timedelta(days=3)).strftime('%Y-%m-%d')}"
            f"?unitGroup=metric"
            f"&elements=datetime,temp,solarradiation,cloudcover,windspeed,precipprob"
            f"&key={api_key}&contentType=json"
        )
        w_res = requests.get(url).json()
        for d in w_res['days']:
            for hr in d['hours']:
                dt = pd.to_datetime(f"{d['datetime']} {hr['datetime']}")
                if dt not in df['Time'].values:
                    df = pd.concat([df, pd.DataFrame([{'Time': dt}])], ignore_index=True)
                mask = df['Time'] == dt
                df.loc[mask, 'Forecast_MW'] = round(float(hr.get('solarradiation', 0)) * 0.0114, 3)
                df.loc[mask, 'CloudCover'] = float(hr.get('cloudcover', 0))
                df.loc[mask, 'Temp'] = float(hr.get('temp', 0))
                df.loc[mask, 'WindSpeed'] = float(hr.get('windspeed', 0))
                df.loc[mask, 'PrecipProb'] = float(hr.get('precipprob', 0))
        print("Погоду оновлено")
    except Exception as e:
        print(f"Погода: {e}")

    if 'Capacity_MW' not in df.columns:
        df['Capacity_MW'] = 12.5
    df['Capacity_MW'] = df['Capacity_MW'].fillna(12.5)

    # Навчаємо модель якщо:
    # 1. Час між 5:00 і 15:00 UTC (8:00-18:00 Київ) — основне вікно
    # 2. АБО прогноз ШІ на сьогодні ще не заповнено (fallback якщо пропустили вікно)
    today_str = now.date()
    ai_col_exists = 'AI_Forecast_MW' in df.columns
    today_mask = pd.to_datetime(df['Time']).dt.date == today_str
    today_has_ai = (
        ai_col_exists and
        (df.loc[today_mask & (df['AI_Forecast_MW'] > 0), 'AI_Forecast_MW'].count() > 0)
    )

    should_train = (5 <= now.hour <= 15) or (not today_has_ai)

    if should_train:
        reason = "вікно 5-15 UTC" if (5 <= now.hour <= 15) else "прогноз на сьогодні відсутній (fallback)"
        print(f"Час {now.hour}:00 UTC — навчаємо модель ({reason})...")
        model, features = train_model(df)
        df = save_ai_forecast(df, model, features)
    else:
        print(f"Час {now.hour}:00 UTC — прогноз вже є на сьогодні, пропускаємо навчання")

    save_df_to_sheet(sheet, df)
    print(f"Готово. Остання дата: {df['Time'].max()}")

if __name__ == "__main__":
    main()
