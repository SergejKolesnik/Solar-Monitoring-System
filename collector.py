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
        forecast_list = []
        for day in res['days']:
            for hr in day['hours']:
                forecast_list.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3)
                })
        return pd.DataFrame(forecast_list)
    except Exception as e:
        print(f"Помилка погоди: {e}")
        return pd.DataFrame()

def get_fact_from_mail():
    print("Починаємо глибокий пошук листів АСКОЕ...")
    askoe_records = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Збільшуємо вікно до 5 днів, щоб точно зачепити 16-те та 17-те
        date_cut = (datetime.now(UA_TZ) - timedelta(days=5)).strftime("%d-%b-%Y")
        status, data = mail.search(None, f'(SINCE "{date_cut}" SUBJECT "ASKOE")')
        
        if status != 'OK': return pd.DataFrame()

        for num in data[0].split():
            _, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            for part in msg.walk():
                filename = part.get_filename()
                if filename and (filename.endswith('.xlsx') or filename.endswith('.csv')):
                    print(f"Знайдено файл: {filename}")
                    payload = part.get_payload(decode=True)
                    
                    # Читаємо файл
                    if filename.endswith('.xlsx'):
                        df_mail = pd.read_excel(io.BytesIO(payload))
                    else:
                        df_mail = pd.read_csv(io.BytesIO(payload))
                    
                    # Гнучке розпізнавання дати та значень
                    for _, row in df_mail.iterrows():
                        try:
                            # Намагаємось перетворити першу колонку на дату, незалежно від формату
                            raw_time = pd.to_datetime(row.iloc[0], dayfirst=True)
                            val = float(str(row.iloc[1]).replace(',', '.'))
                            askoe_records.append({
                                'Time': raw_time.replace(tzinfo=None),
                                'Fact_MW': round(val, 3)
                            })
                        except: continue
        mail.logout()
        return pd.DataFrame(askoe_records)
    except Exception as e:
        print(f"Помилка пошти: {e}")
        return pd.DataFrame()

def sync_all():
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # 1. ПРОГНОЗ (Тільки нові години)
    df_f = get_forecast()
    if not df_f.empty:
        new_hours = df_f[~df_f['Time'].isin(df_base['Time'])]
        df_base = pd.concat([df_base, new_hours], ignore_index=True)

    # 2. ФАКТ (Оновлюємо пропуски за 16-17 число)
    df_fact = get_fact_from_mail()
    if not df_fact.empty:
        # Примусово округляємо час до години для стиковки
        df_fact['Time'] = df_fact['Time'].dt.floor('H')
        df_base['Time'] = df_base['Time'].dt.floor('H')
        
        # Об'єднуємо дані
        for _, row in df_fact.iterrows():
            mask = df_base['Time'] == row['Time']
            if mask.any():
                # Оновлюємо тільки якщо Fact_MW ще порожній
                if pd.isna(df_base.loc[mask, 'Fact_MW']).any():
                    df_base.loc[mask, 'Fact_MW'] = row['Fact_MW']
            else:
                # Якщо прогнозу не було, додаємо новий рядок
                df_base = pd.concat([df_base, pd.DataFrame([row])], ignore_index=True)

    # Збереження
    df_base = df_base.sort_values('Time').drop_duplicates('Time', keep='first')
    df_base.to_csv(CSV_FILE, index=False)
    print("Базу оновлено успішно.")

if __name__ == "__main__":
    sync_all()
