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
LAT, LON = "47.56", "34.39"
UA_TZ = pytz.timezone('Europe/Kyiv')

def get_forecast():
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/next3days?unitGroup=metric&elements=datetime,solarradiation&key={WEATHER_API_KEY}&contentType=json"
        res = requests.get(url, timeout=15).json()
        f_list = []
        for d in res['days']:
            for hr in d['hours']:
                f_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3)
                })
        return pd.DataFrame(f_list)
    except: return pd.DataFrame()

def get_fact_from_mail():
    print("Сканування пошти за структурою НЗФ...")
    records = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        
        date_cut = (datetime.now(UA_TZ) - timedelta(days=7)).strftime("%d-%b-%Y")
        status, data = mail.search(None, f'(SINCE "{date_cut}")')
        
        for num in data[0].split():
            _, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            for part in msg.walk():
                filename = part.get_filename()
                # Шукаємо файли report... або reportCEC...
                if filename and (filename.startswith('report')):
                    print(f"Парсинг файлу: {filename}")
                    payload = part.get_payload(decode=True)
                    
                    # ВАЖЛИВО: пропускаємо перші 2 рядки шапки (skiprows=2)
                    df = pd.read_excel(io.BytesIO(payload), skiprows=2)
                    
                    for _, row in df.iterrows():
                        try:
                            # Колонка A (index 0) - Час
                            # Колонка E (index 4) - Виробіток фотоел. (кВт-год)
                            t_raw = pd.to_datetime(row.iloc[0], dayfirst=True)
                            val_kwh = float(str(row.iloc[4]).replace(',', '.'))
                            
                            # Конвертуємо кВт-год у МВт
                            val_mw = val_kwh / 1000
                            
                            records.append({
                                'Time': t_raw.replace(tzinfo=None).floor('H'),
                                'Fact_MW': round(val_mw, 4)
                            })
                        except: continue
        mail.logout()
        return pd.DataFrame(records)
    except Exception as e:
        print(f"Помилка: {e}")
        return pd.DataFrame()

def sync():
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # Прогноз (тільки нові)
    df_f = get_forecast()
    if not df_f.empty:
        new_h = df_f[~df_f['Time'].isin(df_base['Time'])]
        df_base = pd.concat([df_base, new_h], ignore_index=True)

    # Факт (заповнюємо пропуски)
    df_fact = get_fact_from_mail()
    if not df_fact.empty:
        df_fact = df_fact.drop_duplicates('Time')
        for _, row in df_fact.iterrows():
            mask = df_base['Time'] == row['Time']
            if mask.any():
                # Оновлюємо, якщо порожньо
                if pd.isna(df_base.loc[mask, 'Fact_MW']).any():
                    df_base.loc[mask, 'Fact_MW'] = row['Fact_MW']
            else:
                df_base = pd.concat([df_base, pd.DataFrame([row])], ignore_index=True)

    df_base.sort_values('Time').drop_duplicates('Time', keep='first').to_csv(CSV_FILE, index=False)
    print("Синхронізація виконана під структуру Excel.")

if __name__ == "__main__":
    sync()
