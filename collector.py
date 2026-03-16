import os
import requests
import pandas as pd
import imaplib
import email
from email.header import decode_header
import io
from datetime import datetime, timedelta
import pytz

# НАЛАШТУВАННЯ (Беремо з Secrets GitHub)
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
CSV_FILE = "solar_ai_base.csv"
LAT, LON = "47.56", "34.39"
UA_TZ = pytz.timezone('Europe/Kyiv')

def get_forecast():
    """Отримує прогноз на 3 дні вперед"""
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/next3days?unitGroup=metric&elements=datetime,solarradiation&key={WEATHER_API_KEY}&contentType=json"
        res = requests.get(url, timeout=15).json()
        data = []
        for day in res['days']:
            for hr in day['hours']:
                data.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3)
                })
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def get_fact_from_mail():
    """Парсер твоєї пошти (приклад логіки)"""
    # Тут залишаємо твою робочу логіку парсингу АСКОЕ
    # Важливо, щоб на виході був DataFrame з колонками ['Time', 'Fact_MW']
    return pd.DataFrame() 

def sync():
    # Завантажуємо існуючу базу
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # 1. Оновлюємо прогнози (Майбутнє)
    df_f = get_forecast()
    if not df_f.empty:
        for _, row in df_f.iterrows():
            if row['Time'] not in df['Time'].values:
                df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
            else:
                df.loc[df['Time'] == row['Time'], 'Forecast_MW'] = row['Forecast_MW']

    # 2. Оновлюємо факти (Минуле)
    df_fact = get_fact_from_mail()
    if not df_fact.empty:
        for _, row in df_fact.iterrows():
            df.loc[df['Time'] == row['Time'], 'Fact_MW'] = row['Fact_MW']

    df.sort_values('Time').drop_duplicates('Time', keep='last').to_csv(CSV_FILE, index=False)
    print("Синхронізація завершена.")

if __name__ == "__main__":
    sync()
