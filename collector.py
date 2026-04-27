import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ ПЕРЕВІРКИ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖЕННЯ ТА ПРИМУСОВЕ ВИПРАВЛЕННЯ ВСІЄЇ БАЗИ
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
        
        # ВИПРАВЛЕННЯ: Якщо в будь-якому рядку Fact_MW > 20 (наприклад), ділимо на 1000.
        # Це виправить ті самі "5 ранку", які вже засіли в базі.
        if 'Fact_MW' in df.columns:
            mask = df['Fact_MW'] > 20 
            if mask.any():
                print(f"⚠️ Знайдено {mask.sum()} аномальних значень. Виправляю масштаб...")
                df.loc[mask, 'Fact_MW'] = (df.loc[mask, 'Fact_MW'] / 1000).round(3)
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ПОШТА (АСКОЕ)
    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        _, messages = mail.search(None, 'ALL')
        mail_ids = messages[0].split()

        for num in reversed(mail_ids[-150:]):
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    try:
                        excel_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                        # Шукаємо колонку з генерацією
                        target_col = 5
                        for idx, val in enumerate(excel_df.iloc[1].astype(str)):
                            if "вироб" in val.lower() or "інвертор" in val.lower():
                                target_col = idx
                                break

                        for i in range(2, len(excel_df)):
                            t = pd.to_datetime(excel_df.iloc[i, 0], errors='coerce')
                            val_raw = pd.to_numeric(str(excel_df.iloc[i, target_col]).replace(',', '.'), errors='coerce')
                            
                            if not pd.isna(t) and not pd.isna(val_raw):
                                # ТУТ ЗАВЖДИ ДІЛИМО НА 1000 (кВт -> МВт)
                                v_mwt = round(val_raw / 1000, 3)
                                new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': v_mwt})
                    except: continue
        mail.logout()
    except Exception as e: print(f"❌ Пошта: {e}")

    # 3. ОБ'ЄДНАННЯ (Нові дані ПЕРЕЗАПИСУЮТЬ старі, якщо вони прийшли свіжі)
    if new_facts:
        df_new = pd.DataFrame(new_facts).drop_duplicates('Time')
        # Ми видаляємо старі Fact_MW для тих годин, що прийшли зараз, щоб точно оновити масштаб
        df = df.set_index('Time')
        df_new = df_new.set_index('Time')
        df.update(df_new)
        df = df.reset_index()

    # 4. ПОГОДА
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

    # 5. ФІНАЛЬНЕ ОЧИЩЕННЯ (подвійна перевірка перед збереженням)
    df.loc[df['Fact_MW'] > 20, 'Fact_MW'] = (df['Fact_MW'] / 1000).round(3)
    
    df = df.sort_values('Time').drop_duplicates('Time').tail(1000)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 БАЗУ ОЧИЩЕНО ТА ЗБЕРЕЖЕНО. Помилки о 5 ранку виправлено.")

if __name__ == "__main__":
    main()
