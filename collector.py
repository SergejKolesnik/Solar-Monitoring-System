import os
import requests
import pandas as pd
import imaplib
import email
from email.header import decode_header
import io
from datetime import datetime, timedelta
import pytz

# 1. КОНФІГУРАЦІЯ (Вже налаштована на твої Secrets)
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
CSV_FILE = "solar_ai_base.csv"
LAT, LON = "47.56", "34.39"
UA_TZ = pytz.timezone('Europe/Kyiv')

# --- БЛОК А: ПРОГНОЗ НА МАЙБУТНЄ (3 ДНІ) ---
def get_forecast():
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/next3days?unitGroup=metric&elements=datetime,solarradiation&key={WEATHER_API_KEY}&contentType=json"
        res = requests.get(url, timeout=15).json()
        forecast_data = []
        for day in res['days']:
            for hr in day['hours']:
                forecast_data.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3)
                })
        return pd.DataFrame(forecast_data)
    except: return pd.DataFrame()

# --- БЛОК Б: ТВОЯ ВЧОРАШНЯ ЛОГІКА ПАРСИНГУ ПОШТИ ---
def get_fact_from_mail():
    askoe_records = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Шукаємо листи АСКОЕ за останні 2 дні
        date_cut = (datetime.now(UA_TZ) - timedelta(days=2)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_cut}" SUBJECT "ASKOE")')
        
        for num in data[0].split():
            _, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart': continue
                if part.get('Content-Disposition') is None: continue
                
                filename = part.get_filename()
                if filename and (filename.endswith('.xlsx') or filename.endswith('.csv')):
                    payload = part.get_payload(decode=True)
                    # Читаємо файл (АСКОЕ зазвичай шле Excel)
                    df_mail = pd.read_excel(io.BytesIO(payload)) if filename.endswith('.xlsx') else pd.read_csv(io.BytesIO(payload))
                    
                    # Наша вчорашня логіка мапінгу колонок
                    # Припускаємо, що у файлі є 'Дата/Час' та 'Потужність'
                    for _, row in df_mail.iterrows():
                        askoe_records.append({
                            'Time': pd.to_datetime(row.iloc[0]), # Перша колонка - час
                            'Fact_MW': row.iloc[1]             # Друга колонка - генерація
                        })
        mail.logout()
        return pd.DataFrame(askoe_records)
    except Exception as e:
        print(f"Помилка пошти: {e}")
        return pd.DataFrame()

# --- БЛОК В: СИНХРОНІЗАЦІЯ ---
def sync_all():
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # 1. Оновлюємо прогнози
    df_f = get_forecast()
    if not df_f.empty:
        for _, row in df_f.iterrows():
            if row['Time'] not in df_base['Time'].values:
                df_base = pd.concat([df_base, pd.DataFrame([row])], ignore_index=True)
            else:
                df_base.loc[df_base['Time'] == row['Time'], 'Forecast_MW'] = row['Forecast_MW']

    # 2. Оновлюємо факти
    df_fact = get_fact_from_mail()
    if not df_fact.empty:
        for _, row in df_fact.iterrows():
            # Вписуємо факт там, де час збігається
            df_base.loc[df_base['Time'] == pd.to_datetime(row['Time']), 'Fact_MW'] = row['Fact_MW']

    # Зберігаємо
    df_base.sort_values('Time').drop_duplicates('Time', keep='last').to_csv(CSV_FILE, index=False)
    print("Дані АСКОЕ та Прогноз успішно зведено в CSV.")

if __name__ == "__main__":
    sync_all()
