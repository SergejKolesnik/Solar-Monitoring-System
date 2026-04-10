import pandas as pd
import requests
import os
import fnmatch
from datetime import datetime

BASE_FILE = "solar_ai_base.csv"
START_DATE = "2026-03-23"

def clean_dt(val):
    """Очищення дати від DST та зайвих пробілів"""
    s = str(val).replace('DST', '').replace('dst', '').strip()
    try:
        return pd.to_datetime(s, dayfirst=True)
    except:
        return pd.to_datetime(s, errors='coerce')

def main():
    if not os.path.exists(BASE_FILE):
        # Якщо файл видалено, створюємо пусту структуру
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])
    else:
        df = pd.read_csv(BASE_FILE)
        df['Time'] = df['Time'].apply(clean_dt)
    
    # 1. Фільтруємо базу: тільки від 23 березня 2026 року
    df = df[df['Time'] >= pd.to_datetime(START_DATE)].copy()

    # 2. Зчитуємо дані з Excel-звітів (репортів)
    # Покладіть всі файли report*.xlsx у папку зі скриптом
    files = [f for f in os.listdir('.') if fnmatch.fnmatch(f.lower(), 'report*.xlsx')]
    
    all_reports = []
    for f in files:
        try:
            temp_df = pd.read_excel(f)
            # Беремо перші дві колонки: Час та Потужність
            temp_df = temp_df.iloc[:, [0, 1]]
            temp_df.columns = ['Time', 'Fact_MW']
            temp_df['Time'] = temp_df['Time'].apply(clean_dt)
            all_reports.append(temp_df)
        except Exception as e:
            print(f"Помилка при читанні {f}: {e}")

    if all_reports:
        df_reports = pd.concat(all_reports).dropna(subset=['Time'])
        df_reports = df_reports[df_reports['Time'] >= pd.to_datetime(START_DATE)]
        
        # Об'єднуємо з базою: оновлюємо фактичні значення
        df.set_index('Time', inplace=True)
        df_reports.set_index('Time', inplace=True)
        df.update(df_reports)
        
        # Додаємо нові години з репортів, якщо їх ще немає в базі
        new_hours = df_reports[~df_reports.index.isin(df.index)]
        df = pd.concat([df, new_hours])
        df.reset_index(inplace=True)

    # 3. Дозавантаження прогнозу та погоди для заповнення дірок
    api_key = os.getenv('WEATHER_API_KEY')
    # Запитуємо дані від 23 березня до сьогодні
    end_date = datetime.now().strftime('%Y-%m-%d')
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{START_DATE}/{end_date}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
    
    try:
        res = requests.get(url).json()
        weather_data = []
        for d in res['days']:
            for hr in d['hours']:
                weather_data.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'CloudCover': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0),
                    'PrecipProb': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(weather_data)
        df_w.set_index('Time', inplace=True)
        
        df.set_index('Time', inplace=True)
        # Оновлюємо тільки порожні значення (NaN або 0) у Forecast та погоді
        df.update(df_w, overwrite=False)
        # Додаємо метео для нових годин
        final_df = pd.concat([df, df_w[~df_w.index.isin(df.index)]])
    except Exception as e:
        print(f"Метео не завантажено: {e}")
        final_df = df

    # 4. Фінальне сортування та збереження
    final_df = final_df.sort_index().reset_index()
    final_df = final_df.drop_duplicates(subset=['Time'])
    # Залишаємо Fact_MW як 0 тільки якщо там дійсно немає даних
    final_df['Fact_MW'] = final_df['Fact_MW'].fillna(0)
    
    final_df.to_csv(BASE_FILE, index=False)
    print(f"Базу успішно оновлено з {START_DATE}. Оброблено файлів: {len(files)}")

if __name__ == "__main__":
    main()
