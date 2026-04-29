import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ УНІВЕРСАЛЬНОГО СКАНЕРА: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖЕННЯ БАЗИ
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Перевіряємо листи за останні 15 днів
        date_from = (datetime.now() - timedelta(days=15)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_from}")')
        ids = data[0].split()
        
        print(f"📧 Аналіз {len(ids)} листів...")

        for num in reversed(ids):
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            
            for part in msg.walk():
                if part.get_filename() and ('.xls' in part.get_filename().lower()):
                    try:
                        print(f"📄 Відкриваю: {part.get_filename()}")
                        raw_data = part.get_payload(decode=True)
                        # Читаємо файл, пропускаючи перший технічний рядок
                        excel_df = pd.read_excel(io.BytesIO(raw_data), header=1)
                        
                        # Очищуємо назви колонок від зайвих пробілів
                        excel_df.columns = [str(c).strip() for c in excel_df.columns]
                        
                        # Визначаємо колонку з часом та генерацією
                        time_col = excel_df.columns[0]
                        # Шукаємо колонку, де є слово "інвертор" або просто 5-ту за рахунком
                        gen_col = None
                        for col in excel_df.columns:
                            if "інвертор" in col.lower() or "вироб" in col.lower():
                                gen_col = col
                                break
                        if not gen_col: gen_col = excel_df.columns[5]

                        for _, row in excel_df.iterrows():
                            t = pd.to_datetime(row[time_col], errors='coerce')
                            val_raw = pd.to_numeric(str(row[gen_col]).replace(',', '.'), errors='coerce')
                            
                            if not pd.isna(t) and not pd.isna(val_raw):
                                # Якщо значення > 20 — це кВт (ділимо на 1000), інакше вже МВт
                                v = round(val_raw / 1000, 3) if val_raw > 20 else round(val_raw, 3)
                                new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': v})
                    except Exception as fe: print(f"⚠️ Помилка обробки файлу: {fe}")
        mail.logout()
    except Exception as e: print(f"❌ Помилка пошти: {e}")

    # 2. ОНОВЛЕННЯ БАЗИ (СИЛОВЕ)
    if new_facts:
        df_new = pd.DataFrame(new_facts).drop_duplicates('Time')
        df = df.set_index('Time')
        df_new = df_new.set_index('Time')
        # Оновлюємо існуючі записи (виправляємо нулі або помилки)
        df.update(df_new)
        # Додаємо нові години
        df = pd.concat([df, df_new[~df_new.index.isin(df.index)]]).reset_index()
        print(f"✅ Успішно додано/оновлено фактів: {len(df_new)}")
    else:
        print("📭 Дані у файлах не знайдені. Перевірте формат Excel.")

    # 3. ПОГОДА (Visual Crossing)
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}/{(datetime.now()+timedelta(days=3)).strftime('%Y-%m-%d')}?unitGroup=metric&key={api_key}&contentType=json"
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
    except: pass

    # 4. ЗБЕРЕЖЕННЯ (Останні 1000 рядків)
    df = df.sort_values('Time').drop_duplicates('Time').tail(1000)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 БАЗУ ОНОВЛЕНО. Остання дата в базі: {df['Time'].max()}")

if __name__ == "__main__":
    main()
