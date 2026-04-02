import pandas as pd
import requests
from datetime import datetime, timedelta
import os

# 1. НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"

def clean_date_string(date_val):
    """Видаляє DST та інші завади з дати"""
    if pd.isna(date_val): return date_val
    # Прибираємо "DST", пробіли та зайві символи
    s = str(date_val).replace('DST', '').replace('dst', '').strip()
    return s

def get_weather_actual():
    """Отримує погоду через API Visual Crossing"""
    api_key = os.getenv('WEATHER_API_KEY')
    # Нікополь: останні 2 дні
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
        # Очищуємо дати в базі від DST перед перетворенням
        df_base['Time'] = df_base['Time'].apply(clean_date_string)
        df_base['Time'] = pd.to_datetime(df_base['Time'], dayfirst=True)
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
    df_new['Fact_MW'] = 0.0 # Заглушка для факту, якщо він не підтягнувся

    # 4. Об'єднання
    # Беремо тільки ті години, яких ще немає в базі
    existing_times = df_base['Time'].unique()
    to_add = df_new[~df_new['Time'].isin(existing_times)].copy()

    if not to_add.empty:
        # Прибираємо колонку Rad перед збереженням, щоб не міняти структуру CSV
        if 'Rad' in to_add.columns: to_add = to_add.drop(columns=['Rad'])
        
        df_final = pd.concat([df_base, to_add], ignore_index=True)
        df_final = df_final.sort_values('Time').tail(1000) # Обмежуємо розмір
        
        # 5. Збереження у файл (GitHub Action сам зробить push)
        df_final.to_csv(BASE_FILE, index=False)
        print(f"Успішно додано {len(to_add)} нових записів за квітень.")
    else:
        print("Нових даних не виявлено.")

if __name__ == "__main__":
    main()
