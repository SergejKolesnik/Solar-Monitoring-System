import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 Старт: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖЕННЯ АБО СТВОРЕННЯ БАЗИ
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ОНОВЛЕННЯ ПОГОДИ (Беремо історію + прогноз)
    print("☁️ Оновлення метеоданих...")
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        d_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        d_end = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{d_start}/{d_end}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        
        w_res = requests.get(url).json()
        new_w_rows = []
        for day in w_res['days']:
            for hr in day['hours']:
                new_w_rows.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 0.0114, 3),
                    'CloudCover': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0),
                    'PrecipProb': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(new_w_rows)
        # Злиття: залишаємо старі факти, оновлюємо погоду
        df = pd.merge(df_w, df[['Time', 'Fact_MW']], on='Time', how='left')
    except Exception as e: print(f"❌ Погода: {e}")

    # 3. ЗБІР ГЕНЕРАЦІЇ (Останні 10 днів)
    print("📧 Читання пошти АСКОЕ...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        date_cutoff = (datetime.now() - timedelta(days=10)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_cutoff}")')
        
        for m_id in data[0].split()[-30:]: # Останні 30 листів
            _, m_data = mail.fetch(m_id, "(RFC822)")
            msg = email.message_from_bytes(m_data[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    excel_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                    
                    # Динамічний пошук колонки з генерацією
                    target_col = 5
                    for idx, val in enumerate(excel_df.iloc[1].astype(str)):
                        if "вироб" in val.lower() or "інвертор" in val.lower():
                            target_col = idx
                            break
                    
                    for i in range(2, len(excel_df)):
                        t_raw = pd.to_datetime(excel_df.iloc[i, 0], errors='coerce')
                        val = pd.to_numeric(str(excel_df.iloc[i, target_col]).replace(',', '.'), errors='coerce')
                        if not pd.isna(t_raw) and not pd.isna(val):
                            t_floor = t_raw.replace(minute=0, second=0, microsecond=0)
                            df.loc[df['Time'] == t_floor, 'Fact_MW'] = val
        mail.close()
        mail.logout()
    except Exception as e: print(f"❌ Пошта: {e}")

    # 4. ЗБЕРЕЖЕННЯ
    df = df.sort_values('Time').drop_duplicates('Time', keep='last').tail(800)
    df.to_csv(BASE_FILE, index=False)
    print(f"✅ Готово. Останній час у базі: {df['Time'].max()}")

if __name__ == "__main__":
    main()
