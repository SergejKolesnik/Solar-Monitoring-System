import pandas as pd
import requests
import os
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"
START_DATE = "2026-03-23"

def clean_dt(val):
    s = str(val).replace('DST', '').replace('dst', '').strip()
    try: return pd.to_datetime(s, dayfirst=True)
    except: return pd.to_datetime(s, errors='coerce')

def main():
    # 1. Створюємо ідеальну часову сітку з 23 березня до сьогодні
    end_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_range = pd.date_range(start=START_DATE, end=end_date, freq='h')
    df_ideal = pd.DataFrame({'Time': full_range})
    df_ideal['Time'] = df_ideal['Time'].dt.floor('h')

    # 2. Завантажуємо існуючу базу (якщо є)
    if os.path.exists(BASE_FILE):
        df_base = pd.read_csv(BASE_FILE)
        df_base['Time'] = df_base['Time'].apply(clean_dt)
        # Об'єднуємо сітку з базою, щоб закрити дірки (1-3 квітня)
        df = pd.merge(df_ideal, df_base, on='Time', how='left')
    else:
        df = df_ideal.copy()

    # 3. Зчитуємо ФАКТ з усіх завантажених Excel-репортів
    files = [f for f in os.listdir('.') if f.lower().endswith('.xlsx') and 'report' in f.lower()]
    all_reports = []
    for f in files:
        try:
            temp = pd.read_excel(f).iloc[:, [0, 1]]
            temp.columns = ['Time', 'Fact_MW_new']
            temp['Time'] = temp['Time'].apply(clean_dt).dt.floor('h')
            all_reports.append(temp)
        except: pass

    if all_reports:
        df_rep = pd.concat(all_reports).drop_duplicates(subset=['Time'])
        df = pd.merge(df, df_rep, on='Time', how='left')
        # Оновлюємо колонку Fact_MW новими даними
        if 'Fact_MW' not in df.columns: df['Fact_MW'] = 0.0
        df['Fact_MW'] = df['Fact_MW_new'].combine_first(df['Fact_MW']).fillna(0.0)
        df.drop(columns=['Fact_MW_new'], inplace=True)

    # 4. Заповнюємо ПРОГНОЗ та погоду через API (ретроспективно)
    api_key = os.getenv('WEATHER_API_KEY')
    # Запитуємо архів за весь період, щоб заповнити дірки 1-3 квітня
    w_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{START_DATE}/{datetime.now().strftime('%Y-%m-%d')}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation&key={api_key}&contentType=json"
    
    try:
        res = requests.get(w_url).json()
        w_rows = []
        for d in res['days']:
            for hr in d['hours']:
                w_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW_api': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'CloudCover_api': hr.get('cloudcover', 0),
                    'Temp_api': hr.get('temp', 0)
                })
        df_w = pd.DataFrame(w_rows)
        df = pd.merge(df, df_w, on='Time', how='left')
        
        # Заповнюємо пусті клітинки даними з API
        cols = {'Forecast_MW': 'Forecast_MW_api', 'CloudCover': 'CloudCover_api', 'Temp': 'Temp_api'}
        for target, source in cols.items():
            if target not in df.columns: df[target] = np.nan
            df[target] = df[target].combine_first(df[source])
            df.drop(columns=[source], inplace=True)
    except: pass

    # 5. Збереження чистої, повної бази без дірок
    df = df.sort_values('Time').drop_duplicates(subset=['Time'])
    df.to_csv(BASE_FILE, index=False)
    print(f"✅ Відновлено дірки в базі. Оброблено {len(files)} репортів.")

if __name__ == "__main__":
    main()
