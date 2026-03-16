import requests
import pandas as pd
import os
from datetime import datetime
import pytz

# 1. НАЛАШТУВАННЯ
API_KEY = "ТВІЙ_WEATHER_API_KEY" # Краще використовувати os.environ.get("WEATHER_API_KEY")
LAT, LON = "47.56", "34.39"
CSV_FILE = "solar_ai_base.csv"
UA_TZ = pytz.timezone('Europe/Kyiv')

def get_current_forecast():
    """Отримує прогноз радіації на поточну годину"""
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/today?unitGroup=metric&elements=datetime,solarradiation&key={API_KEY}&contentType=json"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # Визначаємо поточну годину в Нікополі
        now_hour = datetime.now(UA_TZ).hour
        
        # Знаходимо дані для цієї години
        radiation = data['days'][0]['hours'][now_hour].get('solarradiation', 0)
        
        # Базовий розрахунок плану (11.4 MW * 0.001 як коефіцієнт)
        forecast_mw = radiation * 11.4 * 0.001
        return round(forecast_mw, 3)
    except Exception as e:
        print(f"Помилка отримання прогнозу: {e}")
        return 0

def get_askoe_fact():
    """
    Тут має бути твоя логіка отримання даних з АСКОЕ.
    Зараз я ставлю заглушку, заміни її на свій виклик API або парсер.
    """
    # Приклад: fact = requests.get("URL_ТВОГО_АСКОЕ").json()['power']
    return 8.45 # Тимчасове значення для тесту

def update_database():
    # 1. Отримуємо час, факт та прогноз
    now_time = datetime.now(UA_TZ).replace(minute=0, second=0, microsecond=0)
    fact_mw = get_askoe_fact()
    forecast_mw = get_current_forecast()
    
    new_data = {
        'Time': [now_time.strftime('%Y-%m-%d %H:%M:%S')],
        'Fact_MW': [fact_mw],
        'Forecast_MW': [forecast_mw]
    }
    
    df_new = pd.DataFrame(new_data)
    
    # 2. Оновлюємо CSV
    if os.path.exists(CSV_FILE):
        df_old = pd.read_csv(CSV_FILE)
        # Перевіряємо, щоб не було дублікатів по часу
        if now_time.strftime('%Y-%m-%d %H:%M:%S') not in df_old['Time'].values:
            df_final = pd.concat([df_old, df_new], ignore_index=True)
            df_final.to_csv(CSV_FILE, index=False)
            print(f"Дані додано: {now_time} | Факт: {fact_mw} | План: {forecast_mw}")
        else:
            print("Запис для цієї години вже існує.")
    else:
        df_new.to_csv(CSV_FILE, index=False)
        print("Створено новий файл бази даних.")

if __name__ == "__main__":
    update_database()
