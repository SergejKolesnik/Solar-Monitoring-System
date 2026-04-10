import pandas as pd
import requests
import os
import numpy as np
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"
START_DATE = "2026-03-23"

def clean_dt(val):
    s = str(val).replace('DST', '').replace('dst', '').strip()
    try: return pd.to_datetime(s, dayfirst=True).floor('h')
    except: return pd.to_datetime(s, errors='coerce').floor('h')

def get_data_from_excel(file_content):
    """Універсальний зчитувач: розуміє і старі, і нові звіти НЗФ"""
    try:
        # Пробуємо прочитати як новий формат (skiprows=1)
        df_rep = pd.read_excel(file_content, skiprows=1)
        time_col = 'Статистичний час'
        fact_col = 'Виробіток фотоел. (кВт⋅год)' if 'Виробіток фотоел. (кВт⋅год)' in df_rep.columns else 'Вироб.ел.ен.інвертором(кВт/г)'
        
        if time_col not in df_rep.columns:
            # Якщо не знайшли, пробуємо як старий формат (без skiprows)
            df_rep = pd.read_excel(file_content)
            time_col = df_rep.columns[0]
            fact_col = df_rep.columns[1]

        temp = df_rep[[time_col, fact_col]].copy()
        temp.columns = ['Time', 'Fact_MW_new']
        temp['Time'] = temp['Time'].apply(clean_dt)
        # Якщо дані в кВт, переводимо в МВт (якщо значення великі)
        if temp['Fact_MW_new'].max() > 100:
            temp['Fact_MW_new'] = pd.to_numeric(temp['Fact_MW_new'], errors='coerce') / 1000
        return temp.dropna(subset=['Time'])
    except: return pd.DataFrame()

def fetch_email_attachments():
    """Завантаження звітів з пошти Gmail"""
    attachments = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Шукаємо листи за останні 3 дні
        date_cut = (datetime.now() - timedelta(days=3)).strftime("%d-%b-%Y")
        _, messages = mail.search(None, f'(SINCE {date_cut})')
        
        for num in messages[0].split():
            _, msg_data = mail.fetch(num, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    for part in msg.walk():
                        if part.get_content_maintype() == 'multipart': continue
                        if part.get('Content-Disposition') is None: continue
                        filename = part.get_filename()
                        if filename and filename.lower().endswith('.xlsx'):
                            attachments.append(part.get_payload(decode=True))
        mail.logout()
    except Exception as e: print(f"Помилка пошти: {e}")
    return attachments

def main():
    # 1. Сітка часу
    end_date = datetime.now().strftime('%Y-%m-%d %H:00:00')
    full_range = pd.date_range(start=START_DATE, end=end_date, freq='h')
    df_main = pd.DataFrame({'Time': full_range})
    df_main['Time'] = df_main['Time'].dt.floor('h')

    # 2. Завантаження бази
    if os.path.exists(BASE_FILE):
        df_old = pd.read_csv(BASE_FILE)
        df_old['Time'] = pd.to_datetime(df_old['Time']).dt.floor('h')
        df_main = pd.merge(df_main, df_old, on='Time', how='left')

    # 3. Збір даних (Пошта + Локальні файли)
    all_sources = fetch_email_attachments()
    # Також перевіряємо, чи не залишилось чогось у корені
    local_files = [f for f in os.listdir('.') if f.lower().endswith('.xlsx') and 'report' in f.lower()]
    for f in local_files:
        with open(f, 'rb') as file: all_sources.append(file.read())

    fact_frames = []
    for content in all_sources:
        df_res = get_data_from_excel(content)
        if not df_res.empty: fact_frames.append(df_res)

    if fact_frames:
        df_facts = pd.concat(fact_frames).drop_duplicates(subset=['Time'])
        df_main = pd.merge(df_main, df_facts, on='Time', how='left', suffixes=('', '_new'))
        if 'Fact_MW' not in df_main.columns: df_main['Fact_MW'] = 0.0
        if 'Fact_MW_new' in df_main.columns:
            df_main['Fact_MW'] = df_main['Fact_MW_new'].combine_first(df_main['Fact_MW'])
            df_main.drop(columns=['Fact_MW_new'], inplace=True)

    # 4. Відновлення прогнозів (API)
    api_key = os.getenv('WEATHER_API_KEY')
    w_url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{START_DATE}/{datetime.now().strftime('%Y-%m-%d')}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
    
    try:
        w_res = requests.get(w_url).json()
        w_rows = []
        for d in w_res['days']:
            for hr in d['hours']:
                w_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}").floor('h'),
                    'Forecast_MW_api': hr.get('solarradiation', 0) * 11.4 * 0.001,
                    'CloudCover_api': hr.get('cloudcover', 0), 'Temp_api': hr.get('temp', 0),
                    'WindSpeed_api': hr.get('windspeed', 0), 'PrecipProb_api': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_rows).drop_duplicates(subset=['Time'])
        df_main = pd.merge(df_main, df_w, on='Time', how='left')
        
        for col in ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']:
            if col not in df_main.columns: df_main[col] = np.nan
            df_main[col] = df_main[col].combine_first(df_main[col + '_api'])
            df_main.drop(columns=[col + '_api'], inplace=True)
    except: pass

    # 5. Округлення та збереження
    for col in ['Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']:
        if col in df_main.columns:
            df_main[col] = pd.to_numeric(df_main[col], errors='coerce').round(3)

    df_main.sort_values('Time').drop_duplicates(subset=['Time']).to_csv(BASE_FILE, index=False)
    print("✅ Автоматизацію відновлено: Пошта + API + Округлення.")
# Створення локальної копії для безпеки
df_main.to_csv("solar_ai_base_backup.csv", index=False)
print("📂 Резервну копію бази створено автоматично.")
if __name__ == "__main__":
    main()
