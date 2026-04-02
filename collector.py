import pandas as pd
import requests
from datetime import datetime, timedelta
import pytz
import os
from github import Github

# 1. НАЛАШТУВАННЯ
# GitHub токен береться з Secrets вашого репозиторію
GITHUB_TOKEN = os.getenv('GH_TOKEN')
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"
BASE_FILE = "solar_ai_base.csv"
UA_TZ = pytz.timezone('Europe/Kyiv')

def get_weather_data():
    """Отримує фактичну погоду за останні 48 годин"""
    api_key = os.getenv('WEATHER_API_KEY')
    # Координати Нікополя
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
                        'PrecipProb': hr.get('precipprob', 0)
                    })
            return pd.DataFrame(h_list)
    except Exception as e:
        print(f"Помилка погоди: {e}")
    return pd.DataFrame()

def process_askoe_data():
    """Тут логіка отримання даних АСКОЕ (Факт)"""
    # ПРИМІТКА: Тут має бути ваш шлях до джерела АСКОЕ (URL або API)
    # Нижче наведено приклад обробки з урахуванням виправлення DST
    try:
        # Припустимо, ми завантажуємо свіжий звіт
        # df_raw = pd.read_excel("URL_ВАШОГО_АСКОЕ") 
        
        # --- ЦЕЙ БЛОК ВИПРАВЛЯЄ ПОМИЛКУ DST ---
        def clean_date(date_val):
            # Видаляємо "DST" та зайві пробіли
            s = str(date_val).replace('DST', '').strip()
            return pd.to_datetime(s, dayfirst=True, errors='coerce')

        # Приклад застосування до колонки з часом:
        # df_raw['Time'] = df_raw.iloc[:, 0].apply(clean_date)
        # ---------------------------------------
        pass
    except:
        pass

def update_github_base():
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)
    
    # 1. Завантажуємо існуючу базу
    file_content = repo.get_contents(BASE_FILE)
    df_base = pd.read_csv(file_content.download_url)
    df_base['Time'] = pd.to_datetime(df_base['Time'])
    
    # 2. Отримуємо нові дані погоди
    df_weather = get_weather_data()
    if df_weather.empty:
        print("Нових даних погоди немає.")
        return

    # 3. Розраховуємо теоретичний прогноз (Сайт)
    # Коефіцієнт 11.4 для вашої потужності
    df_weather['Forecast_MW'] = (df_weather['Temp'] * 0) + 1.2 # Заглушка, якщо немає рад.
    # Якщо є дані радіації, використовуємо їх:
    # df_weather['Forecast_MW'] = df_weather['Rad'] * 11.4 * 0.001 

    # 4. Об'єднуємо та видаляємо дублікати
    # Ми залишаємо тільки ті години, яких ще немає в базі
    new_rows = df_weather[~df_weather['Time'].isin(df_base['Time'])]
    
    if not new_rows.empty:
        df_updated = pd.concat([df_base, new_rows], ignore_index=True)
        df_updated = df_updated.sort_values('Time').tail(5000) # Тримаємо базу компактною
        
        # 5. Записуємо назад на GitHub
        csv_data = df_updated.to_csv(index=False)
        repo.update_file(
            path=BASE_FILE,
            message=f"Auto-update: {datetime.now(UA_TZ).strftime('%Y-%m-%d %H:%M')}",
            content=csv_data,
            sha=file_content.sha
        )
        print(f"Додано {len(new_rows)} нових рядків.")
    else:
        print("Нових записів для додавання не знайдено.")

if __name__ == "__main__":
    if GITHUB_TOKEN:
        update_github_base()
    else:
        print("Помилка: GH_TOKEN не знайдено в Secrets!")
