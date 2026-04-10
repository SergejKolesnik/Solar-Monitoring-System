import pandas as pd
import requests
import os
import fnmatch
from datetime import datetime

BASE_FILE = "solar_ai_base.csv"
START_DATE = "2026-03-23"

def clean_dt(val):
    s = str(val).replace('DST', '').replace('dst', '').strip()
    try:
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.to_datetime(s, errors='coerce')

def main():
    # 1. Завантаження бази
    if not os.path.exists(BASE_FILE):
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])
    else:
        df = pd.read_csv(BASE_FILE)
        df['Time'] = df['Time'].apply(clean_dt)
    
    # Фільтр від 23 березня
    df = df[df['Time'] >= pd.to_datetime(START_DATE)].copy()
    # КРИТИЧНО: Видаляємо дублікати в базі перед оновленням
    df = df.drop_duplicates(subset=['Time'])

    # 2. Зчитуємо репорти з кореня GitHub
    files = [f for f in os.listdir('.') if fnmatch.fnmatch(f.lower(), 'report*.xlsx')]
    all_reports = []
    for f in files:
        try:
            temp_df = pd.read_excel(f).iloc[:, [0, 1]]
            temp_df.columns = ['Time', 'Fact_MW']
            temp_df['Time'] = temp_df['Time'].apply(clean_dt)
            all_reports.append(temp_df)
        except: pass

    if all_reports:
        df_reports = pd.concat(all_reports).dropna(subset=['Time'])
        df_reports = df_reports[df_reports['Time'] >= pd.to_datetime(START_DATE)]
        # КРИТИЧНО: Видаляємо дублікати в самих репортах
        df_reports = df_reports.drop_duplicates(subset=['Time'])
        
        # Оновлення даних
        df.set_index('Time', inplace=True)
        df_reports.set_index('Time', inplace=True)
        df.update(df_reports)
        
        # Додавання нових годин
        new_hours = df_reports[~df_reports.index.isin(df.index)]
        df = pd.concat([df, new_hours])
        df = df.sort_index().reset_index()
    else:
        if 'Time' not in df.columns: df = df.reset_index()

    # 3. Дозавантаження Метео (Forecast)
    api_key = os.getenv('WEATHER_API_KEY')
    end_date = datetime.now().strftime('%Y-%m-%d')
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{START_DATE}/{end_date}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
    
    try:
        res = requests.get(url).json()
        w_list = []
        for d in res['days']:
            for hr in d['hours']:
                w_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'CloudCover': hr.get('cloudcover', 0), 'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0), 'PrecipProb': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_list).drop_duplicates(subset=['Time']).set_index('Time')
        
        if 'Time' in df.columns: df.set_index('Time', inplace=True)
        df.update(df_w, overwrite=False)
        df = pd.concat([df, df_w[~df_w.index.isin(df.index)]])
    except: pass

    # 4. Збереження
    df = df.sort_index().reset_index().drop_duplicates(subset=['Time'])
    df.to_csv(BASE_FILE, index=False)
    print("✅ Базу успішно очищено від дублікатів та оновлено.")

if __name__ == "__main__":
    main()
