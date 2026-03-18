import os
import requests
import pandas as pd
import imaplib
import email
from email.header import decode_header
import io
from datetime import datetime, timedelta
import pytz

# 1. КОНФІГУРАЦІЯ
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
CSV_FILE = "solar_ai_base.csv"
LAT, LON = "47.56", "34.39"
UA_TZ = pytz.timezone('Europe/Kyiv')

def get_forecast():
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/next3days?unitGroup=metric&elements=datetime,solarradiation&key={WEATHER_API_KEY}&contentType=json"
        res = requests.get(url, timeout=15).json()
        f_list = []
        for d in res['days']:
            for hr in d['hours']:
                f_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3)
                })
        return pd.DataFrame(f_list)
    except Exception as e:
        print(f"Weather error: {e}")
        return pd.DataFrame()

def get_fact_from_mail():
    print("Логін у пошту...")
    records = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        
        # Шукаємо за останні 7 днів БУДЬ-ЯКІ листи (ALL), щоб не пропустити нічого
        date_cut = (datetime.now(UA_TZ) - timedelta(days=7)).strftime("%d-%b-%Y")
        # Шукаємо листи просто за датою (без фільтру по темі в самому пошуку, відфільтруємо в коді)
        status, data = mail.search(None, f'(SINCE "{date_cut}")')
        
        if status != 'OK': return pd.DataFrame()

        mail_ids = data[0].split()
        print(f"Знайдено {len(mail_ids)} листів за тиждень. Перевіряємо вкладення...")

        for num in mail_ids[::-1]: # Йдемо від нових до старих
            _, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            
            # Декодуємо тему
            subject = decode_header(msg.get("Subject", ""))[0][0]
            if isinstance(subject, bytes): subject = subject.decode()
            subject = subject.upper()

            # Якщо в темі є АСКОЕ або ASKOE
            if "ASKOE" in subject or "АСКОЕ" in subject:
                print(f"Обробка листа: {subject}")
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart': continue
                    filename = part.get_filename()
                    
                    if filename and (filename.endswith('.xlsx') or filename.endswith('.csv')):
                        print(f"Зчитування файлу: {filename}")
                        payload = part.get_payload(decode=True)
                        
                        try:
                            df = pd.read_excel(io.BytesIO(payload)) if filename.endswith('.xlsx') else pd.read_csv(io.BytesIO(payload))
                            # Чистимо дані
                            for _, row in df.iterrows():
                                try:
                                    t = pd.to_datetime(row.iloc[0], dayfirst=True).replace(tzinfo=None).floor('H')
                                    v = float(str(row.iloc[1]).replace(',', '.'))
                                    records.append({'Time': t, 'Fact_MW': round(v, 3)})
                                except: continue
                        except Exception as parse_e:
                            print(f"Помилка парсингу файлу: {parse_e}")
                            
        mail.logout()
        return pd.DataFrame(records)
    except Exception as e:
        print(f"Mail error: {e}")
        return pd.DataFrame()

def sync():
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # 1. ПРОГНОЗ (Тільки якщо години немає)
    df_f = get_forecast()
    if not df_f.empty:
        new_rows = df_f[~df_f['Time'].isin(df_base['Time'])]
        df_base = pd.concat([df_base, new_rows], ignore_index=True)

    # 2. ФАКТ (Оновлюємо NaN)
    df_fact = get_fact_from_mail()
    if not df_fact.empty:
        df_fact = df_fact.drop_duplicates('Time')
        for _, row in df_fact.iterrows():
            mask = df_base['Time'] == row['Time']
            if mask.any():
                # Записуємо тільки якщо там ще NaN
                if pd.isna(df_base.loc[mask, 'Fact_MW']).any():
                    df_base.loc[mask, 'Fact_MW'] = row['Fact_MW']
            else:
                # Якщо прогнозу не було - створюємо новий рядок
                df_base = pd.concat([df_base, pd.DataFrame([row])], ignore_index=True)

    df_base = df_base.sort_values('Time').drop_duplicates('Time', keep='first')
    df_base.to_csv(CSV_FILE, index=False)
    print(f"Готово. В базі {len(df_base)} рядків.")

if __name__ == "__main__":
    sync()
