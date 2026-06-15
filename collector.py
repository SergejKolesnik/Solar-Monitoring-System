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
from sklearn.ensemble import HistGradientBoostingRegressor

SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Основні числові колонки, які зберігаються у Google Sheet
NUMERIC_COLS = [
    'Forecast_MW',
    'CloudCover',
    'Temp',
    'WindSpeed',
    'PrecipProb',
    'Fact_MW',
    'Capacity_MW',
    'Forecast_Error_MW',
    'Forecast_Error_Pct',
    'AI_Forecast_MW',
    'AI_Error_MW',
    'AI_Error_Pct'
]

# Базові ознаки для моделі корекції прогнозу
BASE_FEATURE_COLS = [
    'Forecast_MW',
    'CloudCover',
    'Temp',
    'WindSpeed',
    'PrecipProb',
    'Capacity_MW'
]

# Додаткові часові ознаки
TIME_FEATURE_COLS = [
    'Hour',
    'Month',
    'DayOfYear'
]

FEATURE_COLS = BASE_FEATURE_COLS + TIME_FEATURE_COLS


def get_sheet():
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS не знайдено")

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID).sheet1


def ensure_columns(df):
    """Гарантує наявність усіх потрібних колонок."""
    if 'Time' not in df.columns:
        df['Time'] = pd.NaT

    # Видаляємо застарілий стовпець, якщо він колись був у таблиці
    df = df.drop(columns=['AI_MW'], errors='ignore')

    for col in NUMERIC_COLS:
        if col not in df.columns:
            df[col] = 0.0

    return df


def load_df_from_sheet(sheet):
    data = sheet.get_all_records(value_render_option='UNFORMATTED_VALUE')

    if not data:
        df = pd.DataFrame(columns=['Time'] + NUMERIC_COLS)
        return ensure_columns(df)

    df = pd.DataFrame(data)
    df = ensure_columns(df)

    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df[df['Time'].notna()].copy()

    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(',', '.').str.strip(),
            errors='coerce'
        ).fillna(0)

    return df


def save_df_to_sheet(sheet, df):
    """Зберігає дані у Google Sheet у фіксованому порядку колонок."""
    df = ensure_columns(df)
    df = df.drop(columns=['AI_MW'], errors='ignore')
    df = df.sort_values('Time').drop_duplicates('Time').copy()

    save_cols = ['Time'] + NUMERIC_COLS
    other_cols = [c for c in df.columns if c not in save_cols]
    df = df[save_cols + other_cols]

    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).round(3)

    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df[df['Time'].notna()].copy()
    df['Time'] = df['Time'].dt.strftime('%Y-%m-%d %H:%M:%S')

    rows = []
    for _, row in df.iterrows():
        r = []
        for col in df.columns:
            if col == 'Time':
                r.append(str(row[col]))
            elif col in NUMERIC_COLS:
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


def add_time_features(df):
    """Додає часові ознаки для моделі, але не обов'язково зберігає їх у таблицю."""
    df = df.copy()
    t = pd.to_datetime(df['Time'], errors='coerce')

    df['Hour'] = t.dt.hour.fillna(0).astype(int)
    df['Month'] = t.dt.month.fillna(0).astype(int)
    df['DayOfYear'] = t.dt.dayofyear.fillna(0).astype(int)

    return df


def calculate_errors(df):
    """
    Рахує помилки:
    Forecast_Error_MW = Fact_MW - Forecast_MW
    AI_Error_MW = Fact_MW - AI_Forecast_MW

    Відсотки рахуються від Fact_MW.
    Для годин без факту помилки залишаються 0.
    """
    df = ensure_columns(df).copy()

    fact = pd.to_numeric(df['Fact_MW'], errors='coerce').fillna(0)
    forecast = pd.to_numeric(df['Forecast_MW'], errors='coerce').fillna(0)
    ai = pd.to_numeric(df['AI_Forecast_MW'], errors='coerce').fillna(0)

    mask = fact > 0

    df['Forecast_Error_MW'] = 0.0
    df['Forecast_Error_Pct'] = 0.0
    df['AI_Error_MW'] = 0.0
    df['AI_Error_Pct'] = 0.0

    df.loc[mask, 'Forecast_Error_MW'] = (fact[mask] - forecast[mask]).round(3)
    df.loc[mask, 'Forecast_Error_Pct'] = (
        df.loc[mask, 'Forecast_Error_MW'] / fact[mask] * 100
    ).round(1)

    df.loc[mask, 'AI_Error_MW'] = (fact[mask] - ai[mask]).round(3)
    df.loc[mask, 'AI_Error_Pct'] = (
        df.loc[mask, 'AI_Error_MW'] / fact[mask] * 100
    ).round(1)

    return df


def train_model(df):
    """
    Навчає модель НЕ напряму на Fact_MW.

    Нова логіка:
    модель вчиться прогнозувати помилку базового прогнозу:
        Forecast_Error_MW = Fact_MW - Forecast_MW

    Потім AI-прогноз рахується так:
        AI_Forecast_MW = Forecast_MW + predicted_error
    """
    df = ensure_columns(df)
    df = calculate_errors(df)
    df = add_time_features(df)

    features = [c for c in FEATURE_COLS if c in df.columns]

    # Навчаємося тільки там, де є реальний факт і є денна генерація/базовий прогноз
    df_train = df[
        (pd.to_numeric(df['Fact_MW'], errors='coerce').fillna(0) > 0.05) &
        (pd.to_numeric(df['Forecast_MW'], errors='coerce').fillna(0) > 0.05)
    ].copy()

    df_train = df_train.dropna(subset=features)

    if len(df_train) < 20:
        print(f"Недостатньо даних для навчання моделі корекції: {len(df_train)} записів")
        return None, features

    X = df_train[features].fillna(0).astype(float)
    y = df_train['Forecast_Error_MW'].astype(float)

    model = HistGradientBoostingRegressor(
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=15,
        l2_regularization=0.1,
        early_stopping=True,
        random_state=42
    )
    model.fit(X, y)

    mae = abs(y - model.predict(X)).mean()
    print(f"Модель корекції HistGradientBoosting навчена на {len(df_train)} записах")
    print(f"Середня помилка моделі на навчальних даних: {mae:.3f} МВт")

    return model, features


def save_ai_forecast(df, model, features):
    """
    Оновлює AI_Forecast_MW на сьогодні + 3 дні вперед.

    Якщо модель ще не навчена, AI_Forecast_MW = Forecast_MW.
    Це краще, ніж залишати нулі, бо таблиця не втрачає прогноз.
    """
    df = ensure_columns(df).copy()

    today = datetime.now().date()
    forecast_end = today + timedelta(days=3)

    time_col = pd.to_datetime(df['Time'], errors='coerce')
    mask_future = (
        (time_col.dt.date >= today) &
        (time_col.dt.date <= forecast_end)
    )

    df_to_predict = df[mask_future].copy()

    if df_to_predict.empty:
        print("Немає погодних даних для прогнозу")
        return df

    base_forecast = pd.to_numeric(df_to_predict['Forecast_MW'], errors='coerce').fillna(0)

    if model is None:
        preds = base_forecast.tolist()
        print("Модель не навчена — AI_Forecast_MW тимчасово дорівнює Forecast_MW")
    else:
        df_pred = add_time_features(df_to_predict)
        avail_features = [f for f in features if f in df_pred.columns]

        X_pred = df_pred[avail_features].fillna(0).astype(float)
        predicted_error = model.predict(X_pred)
        error_limit = base_forecast.values * 0.30
        predicted_error = [
            min(max(float(err), -float(limit)), float(limit))
            for err, limit in zip(predicted_error, error_limit)
        ]

        preds = base_forecast.values + predicted_error

    # Обмеження: прогноз не може бути нижче 0 і вище встановленої потужності
    capacity = pd.to_numeric(df_to_predict['Capacity_MW'], errors='coerce').fillna(12.5).values

    result = []
    hours = pd.to_datetime(df_to_predict['Time'], errors='coerce').dt.hour.fillna(0).astype(int)

    for p, cap, h in zip(preds, capacity, hours):
        if h < 5 or h > 21:
            result.append(0.0)
        else:
            p = max(0.0, float(p))
            p = min(p, float(cap))
            result.append(round(p, 3))

    df.loc[mask_future, 'AI_Forecast_MW'] = result

    days_count = pd.to_datetime(df_to_predict['Time']).dt.date.nunique()
    non_zero = sum(1 for p in result if p > 0)
    max_p = max(result) if result else 0

    print(
        f"AI_Forecast_MW оновлено: {days_count} дн., "
        f"{non_zero} год. з генерацією, макс {max_p:.3f} МВт"
    )

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


def update_facts(df, facts):
    if not facts:
        print("Нових фактів не знайдено")
        return df

    df_new = pd.DataFrame(facts)
    df_new = df_new.groupby('Time')['Fact_MW'].max().reset_index()

    df = df.set_index('Time')
    df_new = df_new.set_index('Time')

    df.update(df_new)
    df = pd.concat([df, df_new[~df_new.index.isin(df.index)]]).reset_index()

    print(
        f"Фактів: {len(df_new)}, "
        f"діапазон: {df_new['Fact_MW'].min():.3f}..{df_new['Fact_MW'].max():.3f} МВт"
    )

    return df


def update_weather(df, now):
    try:
        api_key = os.getenv('WEATHER_API_KEY')

        if not api_key:
            print("WEATHER_API_KEY не знайдено — погоду не оновлено")
            return df

        url = (
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
            f"47.631494,34.348690/"
            f"{(now - timedelta(days=7)).strftime('%Y-%m-%d')}/"
            f"{(now + timedelta(days=3)).strftime('%Y-%m-%d')}"
            f"?unitGroup=metric"
            f"&elements=datetime,temp,solarradiation,cloudcover,windspeed,precipprob"
            f"&key={api_key}&contentType=json"
        )

        w_res = requests.get(url, timeout=30).json()

        if 'days' not in w_res:
            print(f"Погода: некоректна відповідь API: {w_res}")
            return df

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

    return df


def main():
    now = datetime.now()
    print(f"СТАРТ: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    sheet = get_sheet()
    df = load_df_from_sheet(sheet)
    df = ensure_columns(df)

    print(f"Завантажено: {len(df)} рядків")

    # Читаємо факти з пошти
    facts = read_facts_from_email(days=30)
    df = update_facts(df, facts)

    # Оновлення погоди
    df = update_weather(df, now)

    # Гарантуємо встановлену потужність
    df = ensure_columns(df)

    if 'Capacity_MW' not in df.columns:
        df['Capacity_MW'] = 12.5

    df['Capacity_MW'] = pd.to_numeric(df['Capacity_MW'], errors='coerce').fillna(12.5)
    df.loc[df['Capacity_MW'] <= 0, 'Capacity_MW'] = 12.5

    # Спочатку рахуємо помилки за вже наявними фактами
    df = calculate_errors(df)

    # Навчаємо модель якщо:
    # 1. Час між 5:00 і 15:00 UTC (8:00-18:00 Київ) — основне вікно
    # 2. АБО прогноз ШІ на сьогодні ще не заповнено
    today_date = now.date()
    today_mask = pd.to_datetime(df['Time'], errors='coerce').dt.date == today_date

    today_has_ai = (
        'AI_Forecast_MW' in df.columns and
        (df.loc[today_mask & (pd.to_numeric(df['AI_Forecast_MW'], errors='coerce').fillna(0) > 0), 'AI_Forecast_MW'].count() > 0)
    )

    should_train = (5 <= now.hour <= 15) or (not today_has_ai)

    if should_train:
        reason = "вікно 5-15 UTC" if (5 <= now.hour <= 15) else "прогноз на сьогодні відсутній (fallback)"
        print(f"Час {now.hour}:00 UTC — навчаємо модель корекції ({reason})...")

        model, features = train_model(df)
        df = save_ai_forecast(df, model, features)

        # Після оновлення AI_Forecast_MW ще раз рахуємо AI-помилки
        df = calculate_errors(df)

    else:
        print(f"Час {now.hour}:00 UTC — прогноз вже є на сьогодні, пропускаємо навчання")
        df = calculate_errors(df)

    # Не зберігаємо службові часові ознаки у Google Sheet
    df = df.drop(columns=TIME_FEATURE_COLS, errors='ignore')

    save_df_to_sheet(sheet, df)
    print(f"Готово. Остання дата: {df['Time'].max()}")


if __name__ == "__main__":
    main()
