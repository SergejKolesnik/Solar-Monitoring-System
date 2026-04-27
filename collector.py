import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ ТЕХОГЛЯДУ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 1. ПОШТА: ШУКАЄМО КОНКРЕТНО ТА ГЛИБОКО
    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Замість SINCE, беремо останні 300 повідомлень взагалі (силовий метод)
        status, messages = mail.search(None, 'ALL')
        mail_ids = messages[0].split()
        
        print(f"📧 Всього у скриньці повідомлень: {len(mail_ids)}. Аналізую останні 150...")

        for num in reversed(mail_ids[-150:]):
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            subject = str(email.header.make_header(email.header.decode_header(msg.get("Subject", ""))))
            
            # Шукаємо Excel вкладення
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    try:
                        content = part.get_payload(decode=True)
                        excel_df = pd.read_excel(io.BytesIO(content), header=None)
                        
                        # Корекція колонки (АСКОЕ зазвичай на 5-6 колонці)
                        for i in range(2, len(excel_df)):
                            t = pd.to_datetime(excel_df.iloc[i, 0], errors='coerce')
                            val = pd.to_numeric(str(excel_df.iloc[i, 5]).replace(',', '.'), errors='coerce')
                            if not pd.isna(t) and not pd.isna(val):
                                # Обов'язково МВт (кВт / 1000)
                                v = round(val / 1000, 3) if val > 100 else round(val, 3)
                                new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': v})
                    except: continue
        mail.logout()
    except Exception as e: print(f"❌ Помилка пошти: {e}")

    # 2. СКЛЕЙКА ТА ПОГОДА (Беремо за останні 14 днів)
    if new_facts:
        df_new = pd.DataFrame(new_facts).drop_duplicates('Time')
        df = pd.merge(df, df_new, on='Time', how='outer', suffixes=('_old', ''))
        if 'Fact_MW_old' in df.columns:
            df['Fact_MW'] = df['Fact_MW'].combine_first(df['Fact_MW_old'])
            df = df.drop(columns=['Fact_MW_old'])

    try:
        api_key = os.getenv('WEATHER_API_KEY')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{(datetime.now()-timedelta(days=14)).strftime('%Y-%m-%d')}/{(datetime.now()+timedelta(days=3)).strftime('%Y-%m-%d')}?unitGroup=metric&key={api_key}&contentType=json"
        w_res = requests.get(url).json()
        for d in w_res['days']:
            for hr in d['hours']:
                dt = pd.to_datetime(f"{d['datetime']} {hr['datetime']}")
                if dt not in df['Time'].values:
                    df = pd.concat([df, pd.DataFrame([{'Time': dt}])], ignore_index=True)
                mask = df['Time'] == dt
                df.loc[mask, 'Forecast_MW'] = round(hr.get('solarradiation', 0) * 0.0114, 3)
                df.loc[mask, 'CloudCover'] = hr.get('cloudcover', 0)
                df.loc[mask, 'Temp'] = hr.get('temp', 0)
    except Exception as e: print(f"❌ Погода: {e}")

    # 3. ФІНАЛ
    df = df.sort_values('Time').drop_duplicates('Time').tail(1000)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 Готово. Останній факт: {df.dropna(subset=['Fact_MW'])['Time'].max()}")

if __name__ == "__main__":
    main()
