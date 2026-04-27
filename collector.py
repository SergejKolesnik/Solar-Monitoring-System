import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ ФІКСАЦІЇ МАСШТАБУ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖЕННЯ ІСНУЮЧОЇ БАЗИ
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
        
        # ПРИМУСОВА КОРЕКЦІЯ СТАРИХ ПОМИЛОК (якщо в базі вже є цифри > 50 МВт)
        if 'Fact_MW' in df.columns:
            mask = df['Fact_MW'] > 50  # Ваша станція ~10 МВт, все що більше 50 точно помилка
            if mask.any():
                print(f"⚠️ Виправляю {mask.sum()} помилкових записів у базі...")
                df.loc[mask, 'Fact_MW'] = (df.loc[mask, 'Fact_MW'] / 1000).round(3)
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ПОШТА (АСКОЕ)
    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Беремо останні 150 повідомлень
        _, messages = mail.search(None, 'ALL')
        mail_ids = messages[0].split()
        
        print(f"📩 Аналізую листи...")

        for num in reversed(mail_ids[-150:]):
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    try:
                        excel_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                        
                        # Шукаємо колонку з генерацією (зазвичай 5-та)
                        target_col = 5
                        for idx, val in enumerate(excel_df.iloc[1].astype(str)):
                            if "вироб" in val.lower() or "інвертор" in val.lower():
                                target_col = idx
                                break

                        for i in range(2, len(excel_df)):
                            t = pd.to_datetime(excel_df.iloc[i, 0], errors='coerce')
                            val_raw = pd.to_numeric(str(excel_df.iloc[i, target_col]).replace(',', '.'), errors='coerce')
                            
                            if not pd.isna(t) and not pd.isna(val_raw):
                                # СУВОРА ПРАВИЛО: ЗАВЖДИ ДІЛИМО НА 1000
                                # Це прибере помилки о 5 ранку та о 19 вечора
                                v_mwt = round(val_raw / 1000, 3)
                                new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': v_mwt})
                    except: continue
        mail.logout()
    except Exception as e: print(f"❌ Помилка пошти: {e}")

    # Оновлення фактів
    if new_facts:
        df_new = pd.DataFrame(new_facts).drop_duplicates('Time')
        df = pd.merge(df, df_new, on='Time', how='outer', suffixes=('_old', ''))
        if 'Fact_MW_old' in df.columns:
            # Пріоритет новому (виправленому) значенню
            df['Fact_MW'] = df['Fact_MW'].combine_first(df['Fact_MW_old'])
            df = df.drop(columns=['Fact_MW_old'])

    # 3. ПОГОДА (Visual Crossing)
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
    except Exception as e: print(f"❌ Помилка метео: {e}")

    # 4. ФІНАЛ
    df = df.sort_values('Time').drop_duplicates('Time').tail(1000)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 Базу ПЕРЕФОРМАТОВАНО. Останній факт: {df.dropna(subset=['Fact_MW'])['Time'].max()}")

if __name__ == "__main__":
    main()
