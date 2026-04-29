import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ ФІНАЛЬНОЇ ВЕРСІЇ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
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
        
        date_from = (datetime.now() - timedelta(days=15)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_from}")')
        ids = data[0].split()
        
        print(f"📧 Перевірка {len(ids)} листів...")

        for num in reversed(ids):
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            
            for part in msg.walk():
                if part.get_filename() and ('.xls' in part.get_filename().lower()):
                    try:
                        print(f"📄 Файл: {part.get_filename()}")
                        raw_data = part.get_payload(decode=True)
                        # Читаємо БЕЗ заголовків взагалі, щоб бачити сирі дані
                        excel_df = pd.read_excel(io.BytesIO(raw_data), header=None)
                        
                        # Дані у вашому файлі починаються з 3-го рядка (індекс 2)
                        for i in range(2, len(excel_df)):
                            # Час зазвичай у 1-й колонці (індекс 0)
                            t_raw = excel_df.iloc[i, 0]
                            t = pd.to_datetime(t_raw, errors='coerce')
                            
                            # Генерація у 6-й колонці (індекс 5) - "Вироб.ел.ен.інвертором"
                            val_raw = excel_df.iloc[i, 5]
                            # Очищуємо від пробілів та міняємо кому на крапку
                            val_str = str(val_raw).replace(',', '.').strip()
                            f_val = pd.to_numeric(val_str, errors='coerce')
                            
                            if not pd.isna(t) and not pd.isna(f_val):
                                # Переводимо кВт у МВт
                                final_v = round(f_val / 1000, 3) if f_val > 25 else round(f_val, 3)
                                new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': final_v})
                                
                    except Exception as fe: print(f"⚠️ Помилка: {fe}")
        mail.logout()
    except Exception as e: print(f"❌ Пошта: {e}")

    if new_facts:
        df_new = pd.DataFrame(new_facts).drop_duplicates('Time')
        # Оновлюємо базу
        df = df.set_index('Time')
        df_new = df_new.set_index('Time')
        df.update(df_new)
        df = pd.concat([df, df_new[~df_new.index.isin(df.index)]]).reset_index()
        print(f"✅ Оброблено фактів: {len(df_new)}")
    else:
        print("📭 Дані не знайдені. Можливо, змістилися колонки.")

    # Оновлення погоди
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

    df = df.sort_values('Time').drop_duplicates('Time').tail(1000)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 Базу збережено. Остання дата: {df['Time'].max()}")

if __name__ == "__main__":
    main()
