import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

def main():
    print(f"🚀 Старт системи: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖЕННЯ ІСНУЮЧОЇ БАЗИ
    if os.path.exists(BASE_FILE):
        df_base = pd.read_csv(BASE_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        # Створюємо з нуля, якщо файл зник
        cols = ['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
        df_base = pd.DataFrame(columns=cols)

    # 2. ЗБІР ПОГОДИ (Прогноз на 3 дні вперед + історія за 7 днів)
    print("☁️ Оновлення погоди...")
    try:
        d_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        d_end = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{d_start}/{d_end}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={WEATHER_API_KEY}&contentType=json"
        
        weather_data = requests.get(url).json()
        new_weather = []
        for day in weather_data['days']:
            for hr in day['hours']:
                new_weather.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 0.0114, 3),
                    'CloudCover': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0),
                    'PrecipProb': hr.get('precipprob', 0)
                })
        
        df_weather = pd.DataFrame(new_weather)
        # Оновлюємо базу погодними даними
        df_base = pd.merge(df_weather, df_base[['Time', 'Fact_MW']], on='Time', how='left')
    except Exception as e:
        print(f"❌ Помилка метео: {e}")

    # 3. ЗБІР ГЕНЕРАЦІЇ З ПОШТИ
    print("📧 Перевірка листів АСКОЕ...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Шукаємо листи за останні 10 днів
        date_cutoff = (datetime.now() - timedelta(days=10)).strftime("%d-%b-%Y")
        _, search_data = mail.search(None, f'(SINCE "{date_cutoff}")')
        
        mail_ids = search_data[0].split()
        for m_id in mail_ids[-30:]: # Останні 30 листів
            _, msg_data = mail.fetch(m_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    excel_data = part.get_payload(decode=True)
                    df_excel = pd.read_excel(io.BytesIO(excel_data), header=None)
                    
                    # Гнучкий пошук колонки з генерацією
                    target_col = 5 # за замовчуванням
                    header_row = df_excel.iloc[1].astype(str).tolist()
                    for idx, val in enumerate(header_row):
                        if "вироб" in val.lower() or "інвертор" in val.lower():
                            target_col = idx
                            break
                    
                    # Парсимо рядки з даними
                    for i in range(2, len(df_excel)):
                        row_time = pd.to_datetime(df_excel.iloc[i, 0], errors='coerce')
                        row_val = pd.to_numeric(str(df_excel.iloc[i, target_col]).replace(',', '.'), errors='coerce')
                        
                        if not pd.isna(row_time) and not pd.isna(row_val):
                            t_floor = row_time.replace(minute=0, second=0, microsecond=0)
                            # Записуємо в основну базу
                            df_base.loc[df_base['Time'] == t_floor, 'Fact_MW'] = row_val
        
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")

    # 4. ФІНАЛІЗАЦІЯ
    df_base = df_base.sort_values('Time').drop_duplicates('Time', keep='last')
    # Залишаємо вікно 30 днів для навчання
    df_base = df_base.tail(720) 
    df_base.to_csv(BASE_FILE, index=False)
    print(f"✅ Базу оновлено. Останній запис: {df_base['Time'].max()}")

if __name__ == "__main__":
    main()
