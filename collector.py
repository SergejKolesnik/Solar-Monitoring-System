import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
GEN_FILE = "base_generation.csv"
WET_FILE = "base_weather.csv"
FINAL_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ: {datetime.now()}")

    # 1. ГЕНЕРАЦІЯ
    new_gen = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        _, data = mail.search(None, 'ALL')
        for num in data[0].split()[-50:]: # Остання 50 листів
            _, d = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(d[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                    for i in range(2, len(df)):
                        t = pd.to_datetime(df.iloc[i, 0], errors='coerce')
                        f = pd.to_numeric(str(df.iloc[i, 5]).replace(',', '.'), errors='coerce')
                        if not pd.isna(t) and not pd.isna(f):
                            new_gen.append({'Time': t.floor('h'), 'Fact_MW': f})
        mail.logout()
    except Exception as e: print(f"⚠️ Пошта: {e}")

    # 2. МЕТЕО
    new_wet = []
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}/{(datetime.now()+timedelta(days=3)).strftime('%Y-%m-%d')}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        res = requests.get(url).json()
        for d in res['days']:
            for hr in d['hours']:
                new_wet.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}").floor('h'),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 0.0114, 3),
                    'CloudCover': hr.get('cloudcover', 0), 'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0), 'PrecipProb': hr.get('precipprob', 0)
                })
    except Exception as e: print(f"⚠️ Метео: {e}")

    # 3. ЗБЕРЕЖЕННЯ (Тільки якщо є дані)
    if new_gen:
        df_g = pd.DataFrame(new_gen).drop_duplicates('Time')
        if os.path.exists(GEN_FILE):
            df_g = pd.concat([pd.read_csv(GEN_FILE), df_g]).drop_duplicates('Time')
        df_g.to_csv(GEN_FILE, index=False)

    if new_wet:
        df_w = pd.DataFrame(new_wet).drop_duplicates('Time')
        if os.path.exists(WET_FILE):
            df_w = pd.concat([pd.read_csv(WET_FILE), df_w]).drop_duplicates('Time')
        df_w.to_csv(WET_FILE, index=False)

    # 4. СКЛЕЙКА
    if os.path.exists(GEN_FILE) and os.path.exists(WET_FILE):
        df_f = pd.merge(pd.read_csv(WET_FILE), pd.read_csv(GEN_FILE), on='Time', how='left')
        df_f.tail(720).to_csv(FINAL_FILE, index=False)
        print("✅ БАЗИ СКЛЕЄНО")

if __name__ == "__main__":
    main()
