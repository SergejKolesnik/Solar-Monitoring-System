import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"
DAYS_TO_KEEP = 30 
LIMIT = DAYS_TO_KEEP * 24 

def main():
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📂 Робоча директорія: {os.getcwd()}")
    print(f"📄 Шлях до бази: {os.path.abspath(BASE_FILE)}")
    
    # 1. ЗАВАНТАЖЕННЯ БАЗИ
    if os.path.exists(BASE_FILE):
        df_main = pd.read_csv(BASE_FILE)
        df_main['Time'] = pd.to_datetime(df_main['Time']).dt.floor('h')
        print(f"📋 База завантажена. Рядки: {len(df_main)}. Остання дата: {df_main['Time'].max()}")
    else:
        print("⚠️ База не знайдена, створюємо нову.")
        df_main = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ПОШТА (АСКОЕ)
    fact_data_list = []
    try:
        print("🔐 Підключення до пошти...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        _, data = mail.search(None, 'ALL')
        last_ids = data[0].split()[-50:]
        
        for num in last_ids:
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            date_str = msg.get("Date")
            msg_date = email.utils.parsedate_to_datetime(date_str).replace(tzinfo=None)
            
            if msg_date > (datetime.now() - timedelta(days=7)):
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart': continue
                    filename = part.get_filename()
                    if filename and (filename.endswith(".xlsx") or filename.endswith(".xls")):
                        try:
                            content = part.get_payload(decode=True)
                            df_excel = pd.read_excel(io.BytesIO(content), header=None)
                            if not df_excel.empty:
                                df_excel = df_excel.astype(str).replace({',': '.'}, regex=True)
                                for _, row in df_excel.iterrows():
                                    t = pd.to_datetime(row[0], errors='coerce')
                                    f = pd.to_numeric(row[1], errors='coerce')
                                    if not pd.isna(t) and not pd.isna(f):
                                        fact_data_list.append({'Time': t.floor('h'), 'Fact_MW': f})
                        except Exception as ex:
                            print(f"❌ Помилка Excel {filename}: {ex}")
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")

    # 3. ПОГОДА (Visual Crossing)
    df_w = pd.DataFrame()
    try:
        print("☁️ Запит погоди...")
        api_key = os.getenv('WEATHER_API_KEY')
        d_start = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d')
        d_end = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{d_start}/{d_end}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        
        w_res = requests.get(url).json()
        w_rows = []
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
        df_w = pd.DataFrame(w_rows)
    except Exception as e:
        print(f"❌ Помилка метео: {e}")

    # 4. ОБ'ЄДНАННЯ ТА РОТАЦІЯ
    print("🔄 Синхронізація...")
    df_new_facts = pd.DataFrame(fact_data_list)
    if not df_new_facts.empty:
        df_new_facts = df_new_facts.drop_duplicates('Time', keep='last')

    df_final = pd.concat([df_main, df_w, df_new_facts], ignore_index=True)
    df_final = df_final.sort_values(by=['Time', 'Fact_MW'], na_position='first')
    df_final = df_final.drop_duplicates(subset=['Time'], keep='last')
    df_final = df_final.sort_values('Time').reset_index(drop=True)

    if len(df_final) > LIMIT:
        df_final = df_final.tail(LIMIT)

    df_final[['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']].to_csv(BASE_FILE, index=False)
    
    last_f = df_final.dropna(subset=['Fact_MW'])['Time'].max()
    print(f"💾 ФІНІШ: База оновлена. Рядків: {len(df_final)}. Останній факт: {last_f}")

if __name__ == "__main__":
    main()
