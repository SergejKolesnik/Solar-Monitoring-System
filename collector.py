import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ (Корекція масштабу): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 1. ЧИТАННЯ ПОШТИ (АСКОЕ)
    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        _, data = mail.search(None, 'ALL')
        for num in data[0].split()[-50:]:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    excel_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                    
                    # Шукаємо колонку з генерацією
                    target_col = 5
                    header_row = excel_df.iloc[1].astype(str).tolist()
                    for idx, val in enumerate(header_row):
                        if "вироб" in val.lower() or "інвертор" in val.lower():
                            target_col = idx
                            break

                    for i in range(2, len(excel_df)):
                        t = pd.to_datetime(excel_df.iloc[i, 0], errors='coerce')
                        # КОРЕКЦІЯ: Ділимо на 1000, щоб перевести кВт у МВт або співрозмірні одиниці
                        val_raw = pd.to_numeric(str(excel_df.iloc[i, target_col]).replace(',', '.'), errors='coerce')
                        if not pd.isna(t) and not pd.isna(val_raw):
                            f = round(val_raw / 1000, 3) 
                            new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': f})
        mail.logout()
    except Exception as e: print(f"⚠️ Пошта: {e}")

    if new_facts:
        df_new_gen = pd.DataFrame(new_facts).drop_duplicates('Time')
        df = pd.merge(df, df_new_gen, on='Time', how='outer', suffixes=('', '_new'))
        if 'Fact_MW_new' in df.columns:
            df['Fact_MW'] = df['Fact_MW_new'].combine_first(df['Fact_MW'])
            df = df.drop(columns=['Fact_MW_new'])

    # 2. ПОГОДА (Visual Crossing)
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
                # Погода вже має правильний масштаб (близько 10-15 у піку)
                df.loc[mask, 'Forecast_MW'] = round(hr.get('solarradiation', 0) * 0.0114, 3)
                df.loc[mask, 'CloudCover'] = hr.get('cloudcover', 0)
                df.loc[mask, 'Temp'] = hr.get('temp', 0)
        print("✅ Погода оновлена")
    except Exception as e: print(f"⚠️ Погода: {e}")

    # 3. ФІНАЛІЗАЦІЯ
    df = df.sort_values('Time').drop_duplicates('Time').tail(800)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 Готово. Порядок цифр вирівняно (кВт -> МВт).")

if __name__ == "__main__":
    main()
