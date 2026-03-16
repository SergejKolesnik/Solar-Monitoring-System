import os
import requests
import pandas as pd
import imaplib
import email
from email.header import decode_header
import io
from datetime import datetime, timedelta
import pytz

# 1. ОПЕРАЦІЙНІ НАЛАШТУВАННЯ (Беремо з Secrets)
# Ці змінні НЕ вписуються текстом, а підтягуються системою автоматично
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
IMAP_SERVER = "imap.gmail.com"
CSV_FILE = "solar_ai_base.csv"
LAT, LON = "47.56", "34.39"
UA_TZ = pytz.timezone('Europe/Kyiv')

# --- БЛОК 1: ПРОГНОЗ ПОГОДИ НА 3 ДНІ ---
def get_weather_forecast():
    print("Отримуємо прогноз погоди...")
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/next3days?unitGroup=metric&elements=datetime,solarradiation&key={WEATHER_API_KEY}&contentType=json"
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        forecast_list = []
        for day in data['days']:
            for hr in day['hours']:
                forecast_list.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3)
                })
        return pd.DataFrame(forecast_list)
    except Exception as e:
        print(f"Помилка API погоди: {e}")
        return pd.DataFrame()

# --- БЛОК 2: ПАРСЕР ПОШТИ АСКОЕ ---
def get_askoe_data_from_mail():
    print("Шукаємо дані АСКОЕ в пошті...")
    askoe_data = []
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        # Шукаємо листи від сьогодні та вчора
        today_date = (datetime.now(UA_TZ) - timedelta(days=1)).strftime("%d-%b-%Y")
        status, messages = mail.search(None, f'(SINCE "{today_date}")')
        
        if status == 'OK':
            for num in messages[0].split():
                res, msg_data = mail.fetch(num, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        subject = decode_header(msg["Subject"])[0][0]
                        if isinstance(subject, bytes): subject = subject.decode()
                        
                        # Фільтр за темою листа (заміни на свою тему, якщо треба)
                        if "ASKOE" in subject.upper():
                            for part in msg.walk():
                                if part.get_content_maintype() == 'multipart': continue
                                if part.get('Content-Disposition') is None: continue
                                
                                filename = part.get_filename()
                                if filename and (".csv" in filename or ".xls" in filename):
                                    payload = part.get_payload(decode=True)
                                    # Тут логіка читання твого файлу (приклад для CSV)
                                    df_mail = pd.read_csv(io.BytesIO(payload))
                                    # ПРИПУЩЕННЯ: у файлі є колонки 'Time' та 'Value'
                                    for _, row in df_mail.iterrows():
                                        askoe_data.append({
                                            'Time': pd.to_datetime(row['Time']),
                                            'Fact_MW': row['Value']
                                        })
        mail.logout()
        return pd.DataFrame(askoe_data)
    except Exception as e:
        print(f"Помилка пошти: {e}")
        return pd.DataFrame()

# --- БЛОК 3: СИНХРОНІЗАЦІЯ БАЗИ ---
def sync_all():
    # 1. Завантажуємо існуючий CSV
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # 2. Отримуємо нові дані
    df_forecast = get_weather_forecast()
    df_fact = get_askoe_data_from_mail()

    # 3. Додаємо прогнози наперед
    if not df_forecast.empty:
        for _, row in df_forecast.iterrows():
            if row['Time'] not in df_base['Time'].values:
                # Новий рядок
                df_base = pd.concat([df_base, pd.DataFrame([row])], ignore_index=True)
            else:
                # Оновлюємо існуючий прогноз
                df_base.loc[df_base['Time'] == row['Time'], 'Forecast_MW'] = row['Forecast_MW']

    # 4. Вписуємо факти, де вони збігаються по часу
    if not df_fact.empty:
        for _, row in df_fact.iterrows():
            df_base.loc[df_base['Time'] == row['Time'], 'Fact_MW'] = row['Fact_MW']

    # 5. Зберігаємо результат
    df_base = df_base.sort_values('Time').drop_duplicates('Time', keep='last')
    df_base.to_csv(CSV_FILE, index=False)
    print("Базу даних успішно синхронізовано!")

if __name__ == "__main__":
    sync_all()
