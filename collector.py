import pandas as pd
import requests
import os
import numpy as np
import imaplib
import email
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"
START_DATE = "2026-03-23"

def main():
    # 1. СТВОРЕННЯ ПОВНОЇ СІТКИ ЧАСУ (До сьогоднішньої години)
    now = datetime.now()
    full_range = pd.date_range(start=START_DATE, end=now, freq='h')
    df_main = pd.DataFrame({'Time': full_range})
    df_main['Time'] = df_main['Time'].dt.floor('h')

    # 2. ЗАВАНТАЖЕННЯ ІСНУЮЧОЇ БАЗИ
    if os.path.exists(BASE_FILE):
        df_old = pd.read_csv(BASE_FILE)
        df_old['Time'] = pd.to_datetime(df_old['Time']).dt.floor('h')
        df_main = pd.merge(df_main, df_old, on='Time', how='left')

    # 3. ЧИТАННЯ ПОШТИ (ФАКТ ГЕНЕРАЦІЇ)
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        # Шукаємо за останні 5 днів, щоб нічого не пропустити
        date_cut = (datetime.now() - timedelta(days=5)).strftime("%d-%b-%Y")
        _, messages = mail.search(None, f'(SINCE {date_cut})')
        
        fact_frames = []
        for num in messages[0].split():
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart': continue
                if part.get('Content-Disposition') is None: continue
                filename = part.get_filename()
                if filename and filename.lower().endswith('.xlsx'):
                    content = part.get_payload(decode=True)
                    # Парсинг нового формату НЗФ
                    df_rep = pd.read_excel(content, skiprows=1)
                    t_col = 'Статистичний час'
                    f_col = 'Виробіток фотоел. (кВт⋅год)' if 'Виробіток фотоел. (кВт⋅год)' in df_rep.columns else 'Вироб.ел.ен.інвертором(кВт/г)'
                    if t_col in df_rep.columns:
                        temp = df_rep[[t_col, f_col]].copy()
                        temp.columns = ['Time', 'Fact_MW_new']
                        temp['Time'] = pd.to_datetime(temp['Time']).dt.floor('h')
                        temp['Fact_MW_new'] = pd.to_numeric(temp['Fact_MW_new'], errors='coerce') / 1000
                        fact_frames.append(temp)
        
        if fact_frames:
            df_facts = pd.concat(fact_frames).drop_duplicates(subset=['Time'])
            df_main = pd.merge(df_main, df_facts, on='Time', how='left')
            if 'Fact_MW' not in df_main.columns: df_main['Fact_MW'] = np.nan
            df_main['Fact_MW'] = df_main['Fact_MW_new'].combine_first(df_main['Fact_MW'])
            df_main.drop(columns=['Fact_MW_new'], inplace=True)
        mail.logout()
    except Exception as e: print(f"Помилка пошти: {e}")

    # 4. ЗАПОВНЕННЯ ПРОГНОЗІВ ТА МЕТЕО (API)
    api_key = os.getenv('WEATHER_API_KEY')
    # Запитуємо дані від початку проекту до сьогодні
    w_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{START_DATE}/{now.strftime('%Y-%m-%d')}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
    
    try:
        w_res = requests.get(w_url).json()
        w_rows = []
        for d in w_res['days']:
            for hr in d['hours']:
                w_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}").floor('h'),
                    'Fc_api': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'Cc_api': hr.get('cloudcover', 0), 'Tp_api': hr.get('temp', 0),
                    'Ws_api': hr.get('windspeed', 0), 'Pp_api': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_rows)
        df_main = pd.merge(df_main, df_w, on='Time', how='left')
        
        # Мапінг колонок: якщо в базі NaN, беремо з API
        cols = {'Forecast_MW': 'Fc_api', 'CloudCover': 'Cc_api', 'Temp': 'Tp_api', 'WindSpeed': 'Ws_api', 'PrecipProb': 'Pp_api'}
        for target, source in cols.items():
            if target not in df_main.columns: df_main[target] = np.nan
            df_main[target] = df_main[target].combine_first(df_main[source])
            df_main.drop(columns=[source], inplace=True)
    except Exception as e: print(f"Помилка метео: {e}")

    # 5. ОКРУГЛЕННЯ ТА ЗБЕРЕЖЕННЯ
    for col in ['Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']:
        if col in df_main.columns:
            df_main[col] = pd.to_numeric(df_main[col], errors='coerce').round(3)

    df_main.sort_values('Time').drop_duplicates(subset=['Time']).to_csv(BASE_FILE, index=False)
    print("✅ Базу відновлено: пошта зчитана, пропуски метео заповнені.")

if __name__ == "__main__":
    main()
