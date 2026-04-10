import pandas as pd
import requests
import os
import numpy as np
from datetime import datetime
from github import Github # Потрібно додати PyGithub у requirements.txt

BASE_FILE = "solar_ai_base.csv"
START_DATE = "2026-03-23"

def main():
    # 1. Підготовка часової сітки
    end_date = datetime.now().strftime('%Y-%m-%d %H:00:00')
    full_range = pd.date_range(start=START_DATE, end=end_date, freq='h')
    df_main = pd.DataFrame({'Time': full_range})
    df_main['Time'] = df_main['Time'].dt.floor('h')

    # 2. Завантаження поточної бази
    if os.path.exists(BASE_FILE):
        df_old = pd.read_csv(BASE_FILE)
        df_old['Time'] = pd.to_datetime(df_old['Time']).dt.floor('h')
        df_old = df_old.drop_duplicates(subset=['Time'])
        df_main = pd.merge(df_main, df_old, on='Time', how='left')

    # 3. Обробка репортів та підготовка до архівування
    files = [f for f in os.listdir('.') if f.lower().endswith('.xlsx') and 'report' in f.lower()]
    fact_data = []
    
    # Ініціалізація GitHub клієнта для переміщення файлів
    token = os.getenv('GH_TOKEN')
    if token:
        g = Github(token)
        repo = g.get_repo("SergejKolesnik/Solar-Monitoring-System")
    
    for f in files:
        try:
            df_rep = pd.read_excel(f, skiprows=1)
            time_col = 'Статистичний час'
            fact_col = 'Виробіток фотоел. (кВт⋅год)' if 'Виробіток фотоел. (кВт⋅год)' in df_rep.columns else 'Вироб.ел.ен.інвертором(кВт/г)'
            
            if time_col in df_rep.columns and fact_col in df_rep.columns:
                temp = df_rep[[time_col, fact_col]].copy()
                temp.columns = ['Time', 'Fact_MW_new']
                temp['Time'] = pd.to_datetime(temp['Time']).dt.floor('h')
                temp['Fact_MW_new'] = pd.to_numeric(temp['Fact_MW_new'], errors='coerce') / 1000
                fact_data.append(temp.dropna(subset=['Time']))
                
                # ПЕРЕМІЩЕННЯ В АРХІВ (Тільки якщо є токен)
                if token:
                    content = repo.get_contents(f)
                    repo.create_file(f"archive/{f}", f"Archive report {f}", content.decoded_content)
                    repo.delete_file(content.path, f"Move {f} to archive", content.sha)
                    print(f"📦 Файл {f} переміщено в архів.")
        except Exception as e:
            print(f"Помилка файлу {f}: {e}")

    if fact_data:
        df_all_facts = pd.concat(fact_data).drop_duplicates(subset=['Time'])
        df_main = pd.merge(df_main, df_all_facts, on='Time', how='left')
        if 'Fact_MW' not in df_main.columns: df_main['Fact_MW'] = 0.0
        if 'Fact_MW_new' in df_main.columns:
            df_main['Fact_MW'] = df_main['Fact_MW_new'].combine_first(df_main['Fact_MW'])
            df_main.drop(columns=['Fact_MW_new'], inplace=True)

    # 4. Відновлення прогнозів через API
    api_key = os.getenv('WEATHER_API_KEY')
    w_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{START_DATE}/{datetime.now().strftime('%Y-%m-%d')}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
    
    try:
        w_res = requests.get(w_url).json()
        w_list = []
        for d in w_res['days']:
            for hr in d['hours']:
                w_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}").floor('h'),
                    'Forecast_MW_api': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'CloudCover_api': hr.get('cloudcover', 0), 'Temp_api': hr.get('temp', 0),
                    'WindSpeed_api': hr.get('windspeed', 0), 'PrecipProb_api': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_list).drop_duplicates(subset=['Time'])
        df_main = pd.merge(df_main, df_w, on='Time', how='left')
        
        map_cols = {'Forecast_MW': 'Forecast_MW_api', 'CloudCover': 'CloudCover_api', 
                    'Temp': 'Temp_api', 'WindSpeed': 'WindSpeed_api', 'PrecipProb': 'PrecipProb_api'}
        for target, source in map_cols.items():
            if target not in df_main.columns: df_main[target] = np.nan
            df_main[target] = df_main[target].combine_first(df_main[source])
            df_main.drop(columns=[source], inplace=True)
    except: pass

    # 5. Округлення до 3 знаків та збереження
    num_cols = ['Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    for col in num_cols:
        if col in df_main.columns:
            df_main[col] = pd.to_numeric(df_main[col], errors='coerce').round(3)

    df_main = df_main.sort_values('Time').drop_duplicates(subset=['Time'])
    df_main.to_csv(BASE_FILE, index=False)
    print("✅ Базу оновлено та очищено від старих репортів.")

if __name__ == "__main__":
    main()
