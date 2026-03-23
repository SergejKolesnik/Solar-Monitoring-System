import os
import requests
import pandas as pd
import imaplib
import email
import io
from datetime import datetime, timedelta
import pytz

# 1. КОНФІГУРАЦІЯ
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
CSV_FILE = "solar_ai_base.csv"
# Твої точні координати
LAT, LON = "47.631494", "34.348690"
UA_TZ = pytz.timezone('Europe/Kyiv')

def get_detailed_forecast():
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/next3days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={WEATHER_API_KEY}&contentType=json"
        res = requests.get(url, timeout=15).json()
        forecast_list = []
        for day in res['days']:
            for hr in day['hours']:
                forecast_list.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 4),
                    'CloudCover': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0),
                    'PrecipProb': hr.get('precipprob', 0)
                })
        return pd.DataFrame(forecast_list)
    except Exception as e:
        print(f"Помилка погоди: {e}")
        return pd.DataFrame()

def get_fact_from_mail():
    askoe_records = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        date_cut = (datetime.now(UA_TZ) - timedelta(days=5)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_cut}")')
        
        for num in data[0].split():
            _, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                filename = part.get_filename()
                if filename and filename.startswith('report'):
                    payload = part.get_payload(decode=True)
                    df_mail = pd.read_excel(io.BytesIO(payload), skiprows=2)
                    for _, row in df_mail.iterrows():
                        try:
                            t = pd.to_datetime(row.iloc[0], dayfirst=True).replace(tzinfo=None).floor('H')
                            val_mw = float(str(row.iloc[4]).replace(',', '.')) / 1000
                            askoe_records.append({'Time': t, 'Fact_MW': round(val_mw, 4)})
                        except: continue
        mail.logout()
        return pd.DataFrame(askoe_records)
    except Exception as e:
        print(f"Помилка пошти: {e}")
        return pd.DataFrame()

def sync():
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 1. Додаємо нові прогнози з деталями
    df_f = get_detailed_forecast()
    if not df_f.empty:
        # Оновлюємо тільки ті години, яких ще немає
        new_hours = df_f[~df_f['Time'].isin(df_base['Time'])]
        df_base = pd.concat([df_base, new_hours], ignore_index=True)

    # 2. Додаємо факти
    df_fact = get_fact_from_mail()
    if not df_fact.empty:
        for _, row in df_fact.iterrows():
            mask = df_base['Time'] == row['Time']
            if mask.any():
                df_base.loc[mask, 'Fact_MW'] = row['Fact_MW']

    # Фільтр сміття (тільки березень 2026)
    df_base = df_base[df_base['Time'].dt.year == 2026]
    df_base = df_base[df_base['Time'].dt.month == 3]

    df_base.sort_values('Time').drop_duplicates('Time').to_csv(CSV_FILE, index=False)
    print("База v11.0 оновлена.")

if __name__ == "__main__":
    sync()
