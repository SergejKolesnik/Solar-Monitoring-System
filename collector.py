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

SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
NUMERIC_COLS = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb', 'Fact_MW', 'Capacity_MW']


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
    df['Time'] = pd.to_datetime(df['Time'])
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '.').str.strip(),
                errors='coerce'
            ).fillna(0)
    return df


def save_df_to_sheet(sheet, df):
    df = df.sort_values('Time').drop_duplicates('Time').tail(1000).copy()
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).round(3)
    df['Time'] = df['Time'].astype(str)
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
    sheet.clear()
    sheet.update([df.columns.tolist()] + rows)
    print(f"✅ Google Sheet оновлено. Рядків: {len(df)}")


def read_facts_from_email(days=15):
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
                        print(f"📧 Знайдено {len(ids)} листів у {folder}")
                        break
            except Exception as fe:
                print(f"⚠️ Папка: {fe}")
                continue

        if not ids:
            print("📭 Листів не знайдено")
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
                        print(f"📄 {filename}")
                        raw_data = part.get_payload(decode=True)
                        if not raw_data:
                            continue
                        excel_df = pd.read_excel(io.BytesIO(raw_data), header=None)
                        for i in range(2, len(excel_df)):
                            try:
                                t_raw = excel_df.iloc[i, 0]
                                if t_raw is None or str(t_raw).strip() in ('', 'nan'):
                                    continue
                                t = pd.to_datetime(t_raw, errors='coerce')
                                if pd.isna(t):
                                    continue
                                val_raw = excel_df.iloc[i, 5]
                                if val_raw is None:
                                    continue
                                f_val = pd.to_numeric(
                                    str(val_raw).replace(',', '.').strip(),
                                    errors='coerce'
                                )
                                if pd.isna(f_val):
                                    continue
                                final_v = round(f_val / 1000, 3) if f_val > 25 else round(f_val, 3)
                                facts.append({
                                    'Time': t.to_pydatetime().replace(minute=0, second=0, microsecond=0),
                                    'Fact_MW': final_v
                                })
                            except Exception:
                                continue
                    except Exception as fe:
                        print(f"⚠️ {filename}: {fe}")
            except Exception:
                continue

        mail.logout()
    except Exception as e:
        print(f"❌ Пошта: {e}")
    return facts


def main():
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    sheet = get_sheet()
    df = load_df_from_sheet(sheet)
    print(f"📊 Завантажено: {len(df)} рядків")

    # Читаємо факти за 15 днів
    facts = read_facts_from_email(days=15)

    if facts:
        df_new = pd.DataFrame(facts)
        df_new = df_new.groupby('Time')['Fact_MW'].max().reset_index()
        df = df.set_index('Time')
        df_new = df_new.set_index('Time')
        df.update(df_new)
        df = pd.concat([df, df_new[~df_new.index.isin(df.index)]]).reset_index()
        print(f"✅ Фактів: {len(df_new)}, діапазон: {df_new['Fact_MW'].min():.3f}..{df_new['Fact_MW'].max():.3f} МВт")
    else:
        print("📭 Нових фактів не знайдено")

    # Оновлення погоди
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        url = (
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
            f"47.631494,34.348690/"
            f"{(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}/"
            f"{(datetime.now()+timedelta(days=3)).strftime('%Y-%m-%d')}"
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
                df.loc[mask, 'CloudCover']  = float(hr.get('cloudcover', 0))
                df.loc[mask, 'Temp']        = float(hr.get('temp', 0))
                df.loc[mask, 'WindSpeed']   = float(hr.get('windspeed', 0))
                df.loc[mask, 'PrecipProb']  = float(hr.get('precipprob', 0))
        print("🌤 Погоду оновлено")
    except Exception as e:
        print(f"❌ Погода: {e}")

    # Capacity_MW
    if 'Capacity_MW' not in df.columns:
        df['Capacity_MW'] = 12.5
    df['Capacity_MW'] = df['Capacity_MW'].fillna(12.5)

    save_df_to_sheet(sheet, df)
    print(f"🏁 Готово. Остання дата: {df['Time'].max()}")


if __name__ == "__main__":
    main()
