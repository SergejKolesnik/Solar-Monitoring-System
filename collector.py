import pandas as pd
import requests
import os
from datetime import datetime

BASE_FILE = "solar_ai_base.csv"
START_DATE = "2026-03-23"

def main():
    # 1. Створюємо часову сітку
    end_date = datetime.now().strftime('%Y-%m-%d %H:00:00')
    full_range = pd.date_range(start=START_DATE, end=end_date, freq='h')
    df_main = pd.DataFrame({'Time': full_range})
    df_main['Time'] = df_main['Time'].dt.floor('h')

    # 2. Завантажуємо існуючу базу
    if os.path.exists(BASE_FILE):
        df_old = pd.read_csv(BASE_FILE)
        df_old['Time'] = pd.to_datetime(df_old['Time']).dt.floor('h')
        df_main = pd.merge(df_main, df_old, on='Time', how='left')

    # 3. Зчитування ФАКТУ (Логіка під звіти НЗФ)
    files = [f for f in os.listdir('.') if f.lower().endswith('.xlsx') and 'report' in f.lower()]
    
    fact_data = []
    for f in files:
        try:
            # Пропускаємо 1 рядок, де назва звіту
            df_rep = pd.read_excel(f, skiprows=1)
            
            # Шукаємо потрібні колонки за назвами
            time_col = 'Статистичний час'
            # Пробуємо знайти колонку з виробітком (може бути дві назви)
            fact_col = 'Виробіток фотоел. (кВт⋅год)' if 'Виробіток фотоел. (кВт⋅год)' in df_rep.columns else 'Вироб.ел.ен.інвертором(кВт/г)'
            
            if time_col in df_rep.columns and fact_col in df_rep.columns:
                temp = df_rep[[time_col, fact_col]].copy()
                temp.columns = ['Time', 'Fact_MW_new']
                temp['Time'] = pd.to_datetime(temp['Time']).dt.floor('h')
                # Перетворюємо кВт*год у МВт*год (ділимо на 1000)
                temp['Fact_MW_new'] = pd.to_numeric(temp['Fact_MW_new'], errors='coerce') / 1000
                fact_data.append(temp.dropna(subset=['Time']))
        except: pass

    if fact_data:
        df_all_facts = pd.concat(fact_data).drop_duplicates(subset=['Time'])
        df_main = pd.merge(df_main, df_all_facts, on='Time', how='left')
        if 'Fact_MW' not in df_main.columns: df_main['Fact_MW'] = 0.0
        if 'Fact_MW_new' in df_main.columns:
            df_main['Fact_MW'] = df_main['Fact_MW_new'].combine_first(df_main['Fact_MW']).fillna(0.0)
            df_main.drop(columns=['Fact_MW_new'], inplace=True)

    # 4. Повне заповнення метео (API)
    api_key = os.getenv('WEATHER_API_KEY')
    w_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{START_DATE}/{datetime.now().strftime('%Y-%m-%d')}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
    
    try:
        w_res = requests.get(w_url).json()
        w_list = []
        for d in w_res['days']:
            for hr in d['hours']:
                w_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW_api': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'CloudCover_api': hr.get('cloudcover', 0),
                    'Temp_api': hr.get('temp', 0),
                    'WindSpeed_api': hr.get('windspeed', 0),
                    'PrecipProb_api': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_list)
        df_main = pd.merge(df_main, df_w, on='Time', how='left')
        
        for col in ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']:
            if col not in df_main.columns: df_main[col] = np.nan
            df_main[col] = df_main[col].combine_first(df_main[col + '_api'])
            df_main.drop(columns=[col + '_api'], inplace=True)
    except: pass

    # 5. Збереження
    df_main = df_main.sort_values('Time').drop_duplicates(subset=['Time'])
    df_main.to_csv(BASE_FILE, index=False)
    print("✅ Дані успішно імпортовано зі звітів НЗФ.")

if __name__ == "__main__":
    main()
