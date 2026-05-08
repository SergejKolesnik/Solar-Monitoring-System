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

def get_sheet():
    creds_json = os.getenv('GOOGLE_CREDENTIALS')
    if not creds_json:
        raise Exception("GOOGLE_CREDENTIALS не знайдено в змінних середовища")
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    return sh.sheet1

def load_df_from_sheet(sheet):
    data = sheet.get_all_records()
    if not data:
        return pd.DataFrame(columns=['Time','Fact_MW','Forecast_MW','CloudCover','Temp','WindSpeed','PrecipProb','Capacity_MW'])
    df = pd.DataFrame(data)
    df['Time'] = pd.to_datetime(df['Time'])
    return df

def save_df_to_sheet(sheet, df):
    df = df.sort_values('Time').drop_duplicates('Time').tail(1000)
    df['Time'] = df['Time'].astype(str)
    sheet.clear()
    sheet.update([df.columns.tolist()] + df.fillna('').values.tolist())
    print(f"✅ Google Sheet оновлено. Рядків: {len(df)}")

def main():
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    sheet = get_sheet()
    df = load_df_from_sheet(sheet)
    print(f"📊 Завантажено з Google Sheet: {len(df)} рядків")

    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")

        date_from = (datetime.now() - timedelta(days=15)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_from}")')
        ids = data[0].split()

        print(f"📧 Перевірка {len(ids)} листів...")

        for num in reversed(ids):
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            for part in msg.walk():
                if part.get_filename() and ('.xls' in part.get_filename().lower()):
                    try:
                        print(f"📄 Файл: {part.get_filename()}")
                        raw_data = part.get_payload(decode=True)
                        excel_df = pd.read_excel(io.BytesIO(raw_data), header=None)

                        for i in range(2, len(excel_df)):
                            t_raw = excel_df.iloc[i, 0]
                            t = pd.to_datetime(t_raw, errors='coerce')
                            val_raw = excel_df.iloc[i, 5]
                            val_str = str(val_raw).replace(',', '.').strip()
                            f_val = pd.to_numeric(val_str, errors='coerce')

                            if not pd.isna(t) and not pd.isna(f_val):
                                final_v = round(f_val / 1000, 3) if f_val > 25 else round(f_val, 3)
                                new_facts.append({
                                    'Time': t.replace(minute=0, second=0, microsecond=0),
                                    'Fact_MW': final_v
                                })
                    except Exception as fe:
                        print(f"⚠️ Помилка: {fe}")
        mail.logout()

    except Exception as e:
        print(f"❌ Пошта: {e}")

    if new_facts:
        df_new = pd.DataFrame(new_facts).drop_duplicates('Time')
        df = df.set_index('Time')
        df_new = df_new.set_index('Time')
        df.update(df_new)
        df = pd.concat([df, df_new[~df_new.index.isin(df.index)]]).reset_index()
        print(f"✅ Оброблено фактів: {len(df_new)}")
    else:
        print("📭 Нових фактів не знайдено.")

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
                df.loc[mask, 'Forecast_MW'] = round(hr.get('solarradiation', 0) * 0.0114, 3)
                df.loc[mask, 'CloudCover']  = hr.get('cloudcover', 0)
                df.loc[mask, 'Temp']        = hr.get('temp', 0)
                df.loc[mask, 'WindSpeed']   = hr.get('windspeed', 0)
                df.loc[mask, 'PrecipProb']  = hr.get('precipprob', 0)
        print("🌤 Погоду оновлено")
    except Exception as e:
        print(f"❌ Погода: {e}")

    # Додаємо Capacity_MW якщо немає
    if 'Capacity_MW' not in df.columns:
        df['Capacity_MW'] = 12.5

    save_df_to_sheet(sheet, df)
    print(f"🏁 Готово. Остання дата: {df['Time'].max()}")

if __name__ == "__main__":
    main()
