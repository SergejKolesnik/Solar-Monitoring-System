import pandas as pd
import requests
from datetime import datetime
import os
import fnmatch

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"

def smart_parse_date(date_val):
    """Очищує дату від DST та перетворює її в об'єкт Python"""
    if pd.isna(date_val): return date_val
    # Видаляємо будь-який текст (DST), залишаючи лише цифри та роздільники
    s = str(date_val).replace('DST', '').replace('dst', '').strip()
    try:
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.to_datetime(s, errors='coerce')

def get_weather_actual():
    """Забирає фактичну погоду для заповнення бази"""
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
    except: return pd.DataFrame()

def main():
    if not os.path.exists(BASE_FILE): return
    
    # 1. Завантаження бази
    df_base = pd.read_csv(BASE_FILE)
    df_base['Time'] = df_base['Time'].apply(smart_parse_date)
    
    # 2. Отримання погоди
    df_weather = get_weather_actual()
    if df_weather.empty: return
    
    # Розрахунок теоретичного прогнозу
    df_weather['Forecast_MW'] = df_weather['Rad'] * 11.4 * 0.001
    
    # 3. Синхронізація з поштою (Захист назви файлу)
    # ПРИМІТКА: Тут скрипт має шукати файл за маскою 'report*.xlsx'
    # Це дозволяє ігнорувати зміну номерів місяців (03 -> 04)
    
    # 4. Оновлення бази новим рядками
    existing_times = pd.to_datetime(df_base['Time']).unique()
    to_add = df_weather[~df_weather['Time'].isin(existing_times)].copy()
    
    if not to_add.empty:
        if 'Rad' in to_add.columns: to_add = to_add.drop(columns=['Rad'])
        # Тимчасово ставимо 0 для факту, він оновиться з пошти
        if 'Fact_MW' not in df_base.columns: df_base['Fact_MW'] = 0.0
        to_add['Fact_MW'] = 0.0
        
        df_final = pd.concat([df_base, to_add], ignore_index=True)
        df_final = df_final.sort_values('Time').drop_duplicates('Time').tail(3000)
        df_final.to_csv(BASE_FILE, index=False)
        print(f"Синхронізація успішна. Додано: {len(to_add)} год.")

if __name__ == "__main__":
    main()
