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
    # 1. Завантаження та очищення бази
    if not os.path.exists(BASE_FILE):
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])
    else:
        df = pd.read_csv(BASE_FILE)
        df['Time'] = df['Time'].apply(clean_dt)
    
    df = df[df['Time'] >= pd.to_datetime(START_DATE)].drop_duplicates(subset=['Time']).copy()

    # 2. Зчитування репортів (Покращений пошук факту)
    files = [f for f in os.listdir('.') if f.lower().endswith('.xlsx') and 'report' in f.lower()]
    all_reports = []
    
    for f in files:
        try:
            # Читаємо Excel, ігноруючи заголовки, якщо вони зміщені
            temp_df = pd.read_excel(f)
            # Шукаємо колонку з часом і колонку з цифрами (генерація)
            # Зазвичай це перші дві колонки
            data = temp_df.iloc[:, [0, 1]].copy()
            data.columns = ['Time', 'Fact_MW']
            data['Time'] = data['Time'].apply(clean_dt)
            # Прибираємо рядки, де Факт не є числом
            data['Fact_MW'] = pd.to_numeric(data['Fact_MW'], errors='coerce')
            all_reports.append(data.dropna(subset=['Time']))
        except Exception as e:
            print(f"Помилка файлу {f}: {e}")

    if all_reports:
        df_reports = pd.concat(all_reports).drop_duplicates(subset=['Time'])
        df_reports = df_reports[df_reports['Time'] >= pd.to_datetime(START_DATE)]
        
        # Оновлюємо базу фактичними даними
        df.set_index('Time', inplace=True)
        df_reports.set_index('Time', inplace=True)
        
        # Важливо: використовуємо combine_first, щоб не затерти існуючі дані прогнозу
        df['Fact_MW'] = df_reports['Fact_MW'].combine_first(df['Fact_MW'])
        df.reset_index(inplace=True)
        
        # Додаємо нові години, яких не було в базі
        new_stuff = df_reports[~df_reports.index.isin(df['Time'])]
        if not new_stuff.empty:
            df = pd.concat([df, new_stuff.reset_index()], ignore_index=True)

    # 3. Синхронізація Метео (Forecast)
    api_key = os.getenv('WEATHER_API_KEY')
    end_date = datetime.now().strftime('%Y-%m-%d')
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{START_DATE}/{end_date}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
    
    try:
        res = requests.get(url).json()
        w_data = []
        for d in res['days']:
            for hr in d['hours']:
                w_data.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'CloudCover': hr.get('cloudcover', 0), 'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0), 'PrecipProb': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_data).set_index('Time')
        df.set_index('Time', inplace=True)
        # Оновлюємо порожні значення погоди
        for col in df_w.columns:
            df[col] = df[col].fillna(df_w[col])
        df.reset_index(inplace=True)
    except: pass

    # 4. Фінальне очищення та збереження
    df = df.drop_duplicates(subset=['Time']).sort_values('Time')
    # Залишаємо Fact_MW як 0.0 тільки там, де генерації реально немає (ніч)
    df.to_csv(BASE_FILE, index=False)
    print(f"✅ Успішно! Оброблено {len(files)} репортів. База актуальна.")

if __name__ == "__main__":
    main()
