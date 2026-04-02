import pandas as pd
import requests
from datetime import datetime, timedelta
import os

# 1. НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"

def smart_date_parse(date_val):
    """Універсальний конвертер дат: чистить DST і розуміє різні формати"""
    if pd.isna(date_val): return date_val
    # Прибираємо текст "DST", "dst" та зайві пробіли
    s = str(date_val).replace('DST', '').replace('dst', '').strip()
    # Намагаємось розпізнати дату автоматично
    try:
        return pd.to_datetime(s, dayfirst=True)
    except:
        # Якщо не вийшло (наприклад, формат ISO), пробуємо ще раз без dayfirst
        return pd.to_datetime(s)

def get_weather_actual():
    """Отримує погоду через API Visual Crossing"""
    api_key = os.getenv('WEATHER_API_KEY')
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/last2days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
    
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'CloudCover': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0),
                        'WindSpeed': hr.get('windspeed', 0),
                        'PrecipProb': hr.get('precipprob', 0),
                        'Rad': hr.get('solarradiation', 0)
                    })
            return pd.DataFrame(h_list)
    except Exception as e:
        print(f"Помилка погоди: {e}")
    return pd.DataFrame()

def main():
    # 1. Завантажуємо існуючу базу
    if os.path.exists(BASE_FILE):
        df_base = pd.read_csv(BASE_FILE)
        # Використовуємо наш розумний парсер для всієї колонки Time
        df_base['Time'] = df_base['Time'].apply(smart_date_parse)
    else:
        print("Файл бази не знайдено!")
        return

    # 2. Отримуємо свіжу погоду
    df_new = get_weather_actual()
    if df_new.empty:
        print("Не вдалося отримати нові дані погоди.")
        return

    # 3. Розрахунок теоретичного прогнозу (Сайт)
    df_new['Forecast_MW'] = df_new['Rad'] * 11.4 * 0.001
    if 'Fact_MW' not in df_base.columns: df_base['Fact_MW'] = 0.0

    # 4. Об'єднання
    existing_times = pd.to_datetime(df_base['Time']).unique()
    to_add = df_new[~df_new['Time'].isin(existing_times)].copy()

    if not to_add.empty:
        # Вирівнюємо колонки
        if 'Rad' in to_add.columns: to_add = to_add.drop(columns=['Rad'])
        to_add['Fact_MW'] = 0.0
        
        df_final = pd.concat([df_base, to_add], ignore_index=True)
        # Сортуємо за часом і прибираємо можливі дублікати
        df_final = df_final.sort_values('Time').drop_duplicates('Time').tail(1000)
        
        # 5. Збереження
        df_final.to_csv(BASE_FILE, index=False)
        print(f"Додано нові записи за квітень: {len(to_add)}")
    else:
        print("Нових даних для додавання немає.")

if __name__ == "__main__":
    main()
