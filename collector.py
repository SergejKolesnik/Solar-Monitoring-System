import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖЕННЯ БАЗИ
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
        # Очистка від "гігантських" цифр, якщо такі затесалися
        if 'Fact_MW' in df.columns:
            df.loc[df['Fact_MW'] > 100, 'Fact_MW'] = (df.loc[df['Fact_MW'] > 100, 'Fact_MW'] / 1000).round(3)
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ПОШТА (АСКОЕ) - ГЛИБОКИЙ АНАЛІЗ
    new_facts = []
    try:
        print("🔐 Підключення до пошти...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Шукаємо листи за останні 30 днів (щоб точно закрити дірку з 19 квітня)
        date_cutoff = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_cutoff}")')
        ids = data[0].split()
        print(f"📩 Знайдено {len(ids)} листів для аналізу.")
        
        for num in ids[-150:]: # Перевіряємо останні 150 повідомлень
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    try:
                        excel_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                        target_col = 5
                        # Шукаємо колонку з генерацією
                        for idx, val in enumerate(excel_df.iloc[1].astype(str)):
                            if "вироб" in val.lower() or "інвертор" in val.lower():
                                target_col = idx
                                break

                        for i in range(2, len(excel_df)):
                            t = pd.to_datetime(excel_df.iloc[i, 0], errors='coerce')
                            val_raw = pd.to_numeric(str(excel_df.iloc[i, target_col]).replace(',', '.'), errors='coerce')
                            if not pd.isna(t) and not pd.isna(val_raw):
                                # МАСШТАБУВАННЯ: кВт -> МВт
                                val_mwt = (val_raw / 1000) if val_raw > 100 else val_raw
                                new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': round(val_mwt, 3)})
                    except: continue
        mail.logout()
    except Exception as e: print(f"⚠️ Помилка пошти: {e}")

    # Оновлення фактів
    if new_facts:
        df_new = pd.DataFrame(new_facts).drop_duplicates('Time')
        df = pd.merge(df, df_new, on='Time', how='outer', suffixes=('_old', ''))
        if 'Fact_MW_old' in df.columns:
            df['Fact_MW'] = df['Fact_MW'].combine_first(df['Fact_MW_old'])
            df = df.drop(columns=['Fact_MW_old'])

    # 3. ПОГОДА (Visual Crossing)
    try:
        print("☁️ Оновлення погоди...")
        api_key = os.getenv('WEATHER_API_KEY')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}/{(datetime.now()+timedelta(days=3)).strftime('%Y-%m-%d')}?unitGroup=metric&key={api_key}&contentType=json"
        w_res = requests.get(url).json()
        for day in w_res['days']:
            for hr in day['hours']:
                dt = pd.to_datetime(f"{day['datetime']} {hr['datetime']}")
                if dt not in df['Time'].values:
                    df = pd.concat([df, pd.DataFrame([{'Time': dt}])], ignore_index=True)
                mask = df['Time'] == dt
                df.loc[mask, 'Forecast_MW'] = round(hr.get('solarradiation', 0) * 0.0114, 3)
                df.loc[mask, 'CloudCover'] = hr.get('cloudcover', 0)
                df.loc[mask, 'Temp'] = hr.get('temp', 0)
                df.loc[mask, 'WindSpeed'] = hr.get('windspeed', 0)
                df.loc[mask, 'PrecipProb'] = hr.get('precipprob', 0)
    except Exception as e: print(f"❌ Помилка метео: {e}")

    # 4. ЗБЕРЕЖЕННЯ (до 800 рядків)
    df = df.sort_values('Time').drop_duplicates('Time').tail(800)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 БАЗУ ОНОВЛЕНО. Останній факт: {df.dropna(subset=['Fact_MW'])['Time'].max()}")

if __name__ == "__main__":
    main()
