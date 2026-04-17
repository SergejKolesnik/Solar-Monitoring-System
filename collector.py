import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ ФАЙЛІВ
GEN_FILE = "base_generation.csv"
WET_FILE = "base_weather.csv"
FINAL_FILE = "solar_ai_base.csv"
DAYS_TO_KEEP = 30 

def main():
    print(f"🚀 СТАРТ РОБОТИ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # --- 1. ЗБІР ГЕНЕРАЦІЇ (ПОШТА) ---
    new_gen_rows = []
    try:
        print("🔐 Вхід у пошту...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        _, data = mail.search(None, 'ALL')
        last_ids = data[0].split()[-100:] # Глибокий пошук для закриття дірок

        for num in last_ids:
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            msg_dt = email.utils.parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None)
            
            if msg_dt > (datetime.now() - timedelta(days=10)):
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart': continue
                    filename = part.get_filename()
                    if filename and (filename.endswith(".xlsx") or filename.endswith(".xls")):
                        try:
                            df_excel = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                            # Пошук колонки з генерацією
                            target_col = 5
                            for col_idx in range(len(df_excel.columns)):
                                val = str(df_excel.iloc[1, col_idx]).lower()
                                if 'вироб' in val or 'інвертор' in val:
                                    target_col = col_idx
                                    break
                            
                            for i in range(2, len(df_excel)):
                                row = df_excel.iloc[i]
                                t = pd.to_datetime(row[0], errors='coerce')
                                if pd.isna(t): continue
                                f = pd.to_numeric(str(row[target_col]).replace(',', '.').strip(), errors='coerce')
                                if not pd.isna(f):
                                    new_gen_rows.append({'Time': t.floor('h'), 'Fact_MW': f})
                        except: continue
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")

    # Збереження/Оновлення бази генерації
    df_gen_new = pd.DataFrame(new_gen_rows)
    if os.path.exists(GEN_FILE):
        df_gen_old = pd.read_csv(GEN_FILE)
        df_gen_old['Time'] = pd.to_datetime(df_gen_old['Time'])
        df_gen = pd.concat([df_gen_old, df_gen_new], ignore_index=True)
    else:
        df_gen = df_gen_new
    
    if not df_gen.empty:
        df_gen = df_gen.drop_duplicates('Time', keep='last').sort_values('Time')
        df_gen.to_csv(GEN_FILE, index=False)
        print(f"✅ База ГЕНЕРАЦІЇ оновлена: {len(df_gen)} рядків")

    # --- 2. ЗБІР МЕТЕО (API) ---
    new_wet_rows = []
    try:
        print("☁️ Запит погоди...")
        api_key = os.getenv('WEATHER_API_KEY')
        d_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        d_end = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{d_start}/{d_end}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        
        w_res = requests.get(url).json()
        for d in w_res['days']:
            for hr in d['hours']:
                new_wet_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}").floor('h'),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3),
                    'CloudCover': hr.get('cloudcover', 0), 
                    'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0), 
                    'PrecipProb': hr.get('precipprob', 0)
                })
    except Exception as e:
        print(f"❌ Помилка метео: {e}")

    # Збереження/Оновлення бази погоди
    df_wet_new = pd.DataFrame(new_wet_rows)
    if os.path.exists(WET_FILE):
        df_wet_old = pd.read_csv(WET_FILE)
        df_wet_old['Time'] = pd.to_datetime(df_wet_old['Time'])
        df_wet = pd.concat([df_wet_old, df_wet_new], ignore_index=True)
    else:
        df_wet = df_wet_new
    
    if not df_wet.empty:
        df_wet = df_wet.drop_duplicates('Time', keep='last').sort_values('Time')
        df_wet.to_csv(WET_FILE, index=False)
        print(f"✅ База МЕТЕО оновлена: {len(df_wet)} рядків")

    # --- 3. ФІНАЛЬНА СКЛЕЙКА (ДЛЯ ШІ) ---
    if not df_wet.empty and not df_gen.empty:
        df_final = pd.merge(df_wet, df_gen, on='Time', how='left')
        limit_time = datetime.now() - timedelta(days=DAYS_TO_KEEP)
        df_final = df_final[df_final['Time'] >= limit_time]
        df_final.to_csv(FINAL_FILE, index=False)
        print(f"💾 ФІНІШ: Склеєна база {FINAL_FILE} готова.")
    else:
        print("⚠️ Недостатньо даних для склейки.")

if __name__ == "__main__":
    main()
