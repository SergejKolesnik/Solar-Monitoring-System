import pandas as pd
import requests
import os
import imaplib
import email
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 Старт: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # 1. ЗАВАНТАЖЕННЯ БАЗИ
    if os.path.exists(BASE_FILE):
        df_main = pd.read_csv(BASE_FILE)
        df_main['Time'] = pd.to_datetime(df_main['Time'])
        print(f"📋 База завантажена. Рядків: {len(df_main)}")
    else:
        print("⚠️ База не знайдена, створюємо нову.")
        df_main = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ПОШТА
    fact_data = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        date_cut = (datetime.now() - timedelta(days=5)).strftime("%d-%b-%Y")
        _, messages = mail.search(None, f'(SINCE {date_cut})')
        
        for num in messages[0].split():
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart' or part.get('Content-Disposition') is None: continue
                if part.get_filename() and part.get_filename().lower().endswith('.xlsx'):
                    df_rep = pd.read_excel(part.get_payload(decode=True), skiprows=1)
                    t_col = 'Статистичний час'
                    f_col = 'Виробіток фотоел. (кВт⋅год)' if 'Виробіток фотоел. (кВт⋅год)' in df_rep.columns else 'Вироб.ел.ен.інвертором(кВт/г)'
                    if t_col in df_rep.columns:
                        temp = df_rep[[t_col, f_col]].copy()
                        temp.columns = ['Time', 'Fact_MW']
                        temp['Time'] = pd.to_datetime(temp['Time']).dt.floor('h')
                        temp['Fact_MW'] = pd.to_numeric(temp['Fact_MW'], errors='coerce') / 1000
                        fact_data.append(temp)
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")

    # 3. МЕТЕО API
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        d_start = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        d_end = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{d_start}/{d_end}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        w_res = requests.get(url).json()
        w_rows = []
        for d in w_res['days']:
            for hr in d['hours']:
                w_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3),
                    'CloudCover': hr.get('cloudcover', 0), 'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0), 'PrecipProb': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_rows)
    except Exception as e:
        print(f"❌ Помилка метео: {e}")
        df_w = pd.DataFrame()

    # 4. ОБ'ЄДНАННЯ ТА ЗБЕРЕЖЕННЯ
    if fact_data or not df_w.empty:
        new_df = pd.concat(fact_data) if fact_data else pd.DataFrame()
        if not df_w.empty:
            new_df = pd.merge(new_df, df_w, on='Time', how='outer') if not new_df.empty else df_w
        
        df_final = pd.concat([df_main, new_df]).drop_duplicates(subset=['Time'], keep='last').sort_values('Time')
        df_final.to_csv(BASE_FILE, index=False)
        print(f"✅ Файл збережений локально. Остання дата: {df_final['Time'].max()}")

if __name__ == "__main__":
    main()
