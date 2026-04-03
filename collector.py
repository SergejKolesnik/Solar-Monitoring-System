import pandas as pd
import requests
from datetime import datetime
import os
import fnmatch

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"

def clean_date_string(date_val):
    """Видаляє DST та ігнорує помилки форматів"""
    if pd.isna(date_val): return date_val
    s = str(date_val).replace('DST', '').replace('dst', '').strip()
    try:
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.to_datetime(s, errors='coerce')

def get_weather_actual():
    """Отримує фактичну погоду за останні 2 дні"""
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

def process_askoe_from_email(attachments):
    """Логіка пошуку вкладення за маскою (report*)"""
    for att in attachments:
        # ЗАХИСТ: Шукаємо файл за початком назви, ігноруючи номер місяця
        if fnmatch.fnmatch(att.filename.lower(), 'report*.xlsx'):
            df_raw = pd.read_excel(att.payload)
            # Очищення дат у звіті
            df_raw.iloc[:, 0] = df_raw.iloc[:, 0].apply(clean_date_string)
            return df_raw
    return None

def main():
    if os.path.exists(BASE_FILE):
        df_base = pd.read_csv(BASE_FILE)
        df_base['Time'] = df_base['Time'].apply(clean_date_string)
    else: return

    df_weather = get_weather_actual()
    if df_weather.empty: return

    # Розрахунок прогнозу сайту
    df_weather['Forecast_MW'] = df_weather['Rad'] * 11.4 * 0.001
    
    # Об'єднання (тільки нові години)
    existing_times = pd.to_datetime(df_base['Time']).unique()
    to_add = df_weather[~df_weather['Time'].isin(existing_times)].copy()

    if not to_add.empty:
        if 'Rad' in to_add.columns: to_add = to_add.drop(columns=['Rad'])
        to_add['Fact_MW'] = 0.0 # Факт додасться при наступній синхронізації пошти
        
        df_final = pd.concat([df_base, to_add], ignore_index=True)
        df_final = df_final.sort_values('Time').drop_duplicates('Time').tail(2000)
        df_final.to_csv(BASE_FILE, index=False)
        print(f"Додано годин: {len(to_add)}")

if __name__ == "__main__":
    main()
