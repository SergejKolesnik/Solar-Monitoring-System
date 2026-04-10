import pandas as pd
import requests
from datetime import datetime
import os
import fnmatch

BASE_FILE = "solar_ai_base.csv"

def clean_datetime(val):
    """Видаляє DST та виправляє формати для квітня"""
    s = str(val).replace('DST', '').replace('dst', '').strip()
    try:
        # Спершу пробуємо стандартний формат
        return pd.to_datetime(s, dayfirst=True)
    except:
        # Якщо не виходить, пробуємо автоматичне розпізнавання
        return pd.to_datetime(s, errors='coerce')

def main():
    if not os.path.exists(BASE_FILE): return
    
    # 1. Читаємо базу
    df_base = pd.read_csv(BASE_FILE)
    df_base['Time'] = df_base['Time'].apply(clean_datetime)
    
    # 2. Отримуємо погоду (вона зазвичай працює добре)
    api_key = os.getenv('WEATHER_API_KEY')
    w_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/last2days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation&key={api_key}&contentType=json"
    
    try:
        res = requests.get(w_url, timeout=15).json()
        weather_rows = []
        for d in res['days']:
            for hr in d['hours']:
                weather_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'CloudCover': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0)
                })
        df_w = pd.DataFrame(weather_rows)
    except: return

    # 3. ТЕРМІНОВЕ ПИТАННЯ: ОНОВЛЕННЯ ФАКТУ ТА ПРОГНОЗУ САЙТУ
    # Ми проходимо по всіх рядках бази, де зараз стоять нулі за квітень
    # І замінюємо їх на свіжі дані з погодного сервера
    df_base.set_index('Time', inplace=True)
    df_w.set_index('Time', inplace=True)
    
    # Оновлюємо прогноз сайту та метео (якщо в базі були нулі)
    df_base.update(df_w)
    
    # 4. ЗБЕРЕЖЕННЯ
    df_base.reset_index(inplace=True)
    # Захист від дублікатів і сортування
    df_base = df_base.drop_duplicates(subset=['Time']).sort_values('Time').tail(2000)
    df_base.to_csv(BASE_FILE, index=False)
    print("Дані за квітень синхронізовано.")

if __name__ == "__main__":
    main()
