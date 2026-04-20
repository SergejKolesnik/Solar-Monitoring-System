import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ (Масштабування кВт -> МВт): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖЕННЯ БАЗИ
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ПЕРЕВІРКА ПОШТИ (АСКОЕ) - ГЛИБОКИЙ ПОШУК
    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        # Шукаємо останні 100 листів, щоб знайти 14-те число
        _, data = mail.search(None, 'ALL')
        ids = data[0].split()[-100:] 
        
        for num in ids:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    try:
                        excel_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                        
                        # Автопошук колонки з генерацією
                        target_col = 5
                        header_row = excel_df.iloc[1].astype(str).tolist()
                        for idx, val in enumerate(header_row):
                            if "вироб" in val.lower() or "інвертор" in val.lower():
                                target_col = idx
                                break

                        for i in range(2, len(excel_df)):
                            t = pd.to_datetime(excel_df.iloc[i, 0], errors='coerce')
                            val_raw = pd.to_numeric(str(excel_df.iloc[i, target_col]).replace(',', '.'), errors='coerce')
                            
                            if not pd.isna(t) and not pd.isna(val_raw):
                                # МАСШТАБУВАННЯ: кВт перетворюємо на МВт
                                # Наприклад: 2600 кВт стає 2.6
                                f = round(val_raw / 1000, 3) 
                                new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': f})
                    except: continue
        mail.logout()
    except Exception as e: print(f"⚠️ Пошта: {e}")

    # Оновлюємо факти в базі (перезаписуємо старі тисячі новими одиницями)
    if new_facts:
        df_new_gen = pd.DataFrame(new_facts).drop_duplicates('Time')
        # Видаляємо стару колонку Fact_MW для тих годин, де прийшли нові відмасштабовані дані
        df = pd.merge(df, df_new_gen, on='Time', how='outer', suffixes=('_old', ''))
        if 'Fact_MW_old' in df.columns:
            # Пріоритет новим відмасштабованим даним
            df['Fact_MW'] = df['Fact_MW'].combine_first(df['Fact_MW_old'])
            df = df.drop(columns=['Fact_MW_old'])

    # 3. ОНОВЛЕННЯ ПОГОДИ
    try:
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
    except Exception as e: print(f"⚠️ Погода: {e}")

    # 4. ФІНАЛІЗАЦІЯ (800 рядків ~ 33 дні)
    df = df.sort_values('Time').drop_duplicates('Time').tail(800)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 БАЗУ ОНОВЛЕНО ТА ВІДМАСШТАБОВАНО")

if __name__ == "__main__":
    main()
