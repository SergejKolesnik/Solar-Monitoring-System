import pandas as pd
import requests
import imaplib
import email
import os
from datetime import datetime, timedelta
import pytz

# 1. КОНФІГУРАЦІЯ (Налаштуй ці змінні або використай Secrets)
WEATHER_API_KEY = "ТВІЙ_API_KEY"
EMAIL_USER = "ТВОЯ_ПОШТА"
EMAIL_PASS = "ТВІЙ_ПАРОЛЬ_ДОДАТКУ"
IMAP_SERVER = "imap.gmail.com"
CSV_FILE = "solar_ai_base.csv"
LAT, LON = "47.56", "34.39"
UA_TZ = pytz.timezone('Europe/Kyiv')

# --- БЛОК 1: ОТРИМАННЯ ПРОГНОЗУ (МАЙБУТНЄ) ---
def get_weather_forecast_3days():
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/next3days?unitGroup=metric&elements=datetime,solarradiation&key={WEATHER_API_KEY}&contentType=json"
        res = requests.get(url, timeout=15).json()
        forecast_data = []
        for day in res['days']:
            for hr in day['hours']:
                forecast_data.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3)
                })
        return pd.DataFrame(forecast_data)
    except Exception as e:
        print(f"Помилка погоди: {e}")
        return pd.DataFrame()

# --- БЛОК 2: ПАРСЕР ПОШТИ (МИНУЛЕ) ---
def parse_askoe_from_mail():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Шукаємо листи за останню добу
        date_cut = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_cut}" SUBJECT "ASKOE")')
        
        askoe_records = []
        for num in data[0].split():
            _, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            # Тут твоя логіка витягування даних з тіла листа або Excel-вкладення
            # Приклад додавання даних:
            # askoe_records.append({'Time': '2026-03-15 12:00:00', 'Fact_MW': 8.45})
        
        mail.logout()
        return pd.DataFrame(askoe_records)
    except Exception as e:
        print(f"Помилка пошти: {e}")
        return pd.DataFrame()

# --- БЛОК 3: СИНХРОНІЗАЦІЯ ТА ЗБЕРЕЖЕННЯ ---
def update_solar_database():
    # Отримуємо нові дані
    df_weather = get_weather_forecast_3days()
    df_mail = parse_askoe_from_mail()
    
    # Завантажуємо існуючу базу
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # Крок А: Додаємо або оновлюємо прогнози (наперед)
    if not df_weather.empty:
        for _, row in df_weather.iterrows():
            if row['Time'] not in df_base['Time'].values:
                new_row = pd.DataFrame({'Time': [row['Time']], 'Forecast_MW': [row['Forecast_MW']]})
                df_base = pd.concat([df_base, new_row], ignore_index=True)
            else:
                df_base.loc[df_base['Time'] == row['Time'], 'Forecast_MW'] = row['Forecast_MW']

    # Крок Б: Вписуємо факти АСКОЕ у відповідні рядки (постфактум)
    if not df_mail.empty:
        for _, row in df_mail.iterrows():
            df_base.loc[df_base['Time'] == pd.to_datetime(row['Time']), 'Fact_MW'] = row['Fact_MW']

    # Фінальне чищення: сортування та видалення дублікатів
    df_base = df_base.sort_values('Time').drop_duplicates('Time', keep='last')
    df_base.to_csv(CSV_FILE, index=False)
    print(f"Базу оновлено: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    update_solar_database()
