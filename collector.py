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
    print(f"🚀 Запуск збору даних: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 1. ЗАВАНТАЖЕННЯ ІСНУЮЧОЇ БАЗИ
    if os.path.exists(BASE_FILE):
        df_main = pd.read_csv(BASE_FILE)
        df_main['Time'] = pd.to_datetime(df_main['Time'])
    else:
        df_main = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])
        df_main['Time'] = pd.to_datetime(df_main['Time'])

    # 2. ЧИТАННЯ ПОШТИ (ФАКТ ГЕНЕРАЦІЇ)
    fact_data = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Шукаємо за останні 3 дні (свіжі звіти)
        date_cut = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        _, messages = mail.search(None, f'(SINCE {date_cut})')
        
        for num in messages[0].split():
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None: continue
                filename = part.get_filename()
                if filename and filename.lower().endswith('.xlsx'):
                    content = part.get_payload(decode=True)
                    df_rep = pd.read_excel(content, skiprows=1)
                    
                    t_col = 'Статистичний час'
                    f_col = 'Виробіток фотоел. (кВт⋅год)' if 'Виробіток фотоел. (кВт⋅год)' in df_rep.columns else 'Вироб.ел.ен.інвертором(кВт/г)'
                    
                    if t_col in df_rep.columns:
                        temp = df_rep[[t_col, f_col]].copy()
                        temp.columns = ['Time', 'Fact_MW']
                        temp['Time'] = pd.to_datetime(temp['Time']).dt.floor('h')
                        temp['Fact_MW'] = pd.to_numeric(temp['Fact_MW'], errors='coerce') / 1000
                        fact_data.append(temp)
        mail.logout()
        print(f"📥 Оброблено листів з пошти: {len(fact_data)}")
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")

    # 3. ЗАВАНТАЖЕННЯ МЕТЕО (API) - ТІЛЬКИ СВІЖІ ДАНІ
    w_rows = []
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        # Запитуємо лише останні 3 дні, щоб не перевантажувати API
        date_start_w = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        date_end_w = datetime.now().strftime('%Y-%m-%d')
        
        w_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{date_start_w}/{date_end_w}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        
        w_res = requests.get(w_url, timeout=15).json()
        for d in w_res['days']:
            for hr in d['hours']:
                w_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}").floor('h'),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3),
                    'CloudCover': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0),
                    'PrecipProb': hr.get('precipprob', 0)
                })
        print(f"🌤 Отримано метеоданих: {len(w_rows)} годин")
    except Exception as e:
        print(f"❌ Помилка метео: {e}")

    # 4. ОБ'ЄДНАННЯ ТА ОНОВЛЕННЯ
    new_data = pd.DataFrame()
    
    if fact_data:
        new_data = pd.concat(fact_data)
    
    if w_rows:
        df_w = pd.DataFrame(w_rows)
        if not new_data.empty:
            new_data = pd.merge(new_data, df_w, on='Time', how='outer')
        else:
            new_data = df_w

    if not new_data.empty:
        # Об'єднуємо стару базу з новою, видаляючи дублікати (пріоритет новим даним)
        df_final = pd.concat([df_main, new_data]).drop_duplicates(subset=['Time'], keep='last')
        df_final = df_final.sort_values('Time')
        
        # Запис у файл
        df_final.to_csv(BASE_FILE, index=False)
        print(f"✅ Базу оновлено. Останній запис: {df_final['Time'].max()}")
    else:
        print("⚠️ Нових даних не знайдено.")

if __name__ == "__main__":
    main()
