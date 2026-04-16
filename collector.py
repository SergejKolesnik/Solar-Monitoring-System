import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"
DAYS_TO_KEEP = 30  # Термін зберігання даних
LIMIT = DAYS_TO_KEEP * 24  # Кількість рядків (720)

def main():
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # --- 1. ЗАВАНТАЖЕННЯ БАЗИ ---
    if os.path.exists(BASE_FILE):
        df_main = pd.read_csv(BASE_FILE)
        df_main['Time'] = pd.to_datetime(df_main['Time'])
        print(f"📋 База завантажена. Рядки: {len(df_main)}. Остання дата: {df_main['Time'].max()}")
    else:
        print("⚠️ База не знайдена, створюємо нову структуру.")
        df_main = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # --- 2. ПОШТА (АСКОЕ) ---
    fact_data_list = []
    try:
        print("🔐 Підключення до пошти...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Перевіряємо останні 50 листів
        _, data = mail.search(None, 'ALL')
        msg_ids = data[0].split()
        last_ids = msg_ids[-50:]
        
        print(f"📩 Аналіз останніх {len(last_ids)} листів...")

        for num in last_ids:
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            date_str = msg.get("Date")
            msg_date = email.utils.parsedate_to_datetime(date_str).replace(tzinfo=None)
            
            # Беремо листи лише за останній тиждень
            if msg_date > (datetime.now() - timedelta(days=7)):
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart': continue
                    filename = part.get_filename()
                    
                    if filename and (filename.endswith(".xlsx") or filename.endswith(".xls")):
                        try:
                            content = part.get_payload(decode=True)
                            df_excel = pd.read_excel(io.BytesIO(content), header=None)
                            
                            if not df_excel.empty:
                                # Виправляємо коми на крапки та шукаємо дані
                                df_excel = df_excel.astype(str).replace({',': '.'}, regex=True)
                                temp_rows = []
                                for _, row in df_excel.iterrows():
                                    t = pd.to_datetime(row[0], errors='coerce')
                                    f = pd.to_numeric(row[1], errors='coerce')
                                    if not pd.isna(t) and not pd.isna(f):
                                        temp_rows.append({'Time': t, 'Fact_MW': f})
                                
                                if temp_rows:
                                    fact_data_list.append(pd.DataFrame(temp_rows))
                        except Exception as ex:
                            print(f"❌ Помилка Excel {filename}: {ex}")
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")

    # --- 3. ПОГОДА (Visual Crossing) ---
    df_w = pd.DataFrame()
    try:
        print("☁️ Запит погоди...")
        api_key = os.getenv('WEATHER_API_KEY')
        d_start = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
        d_end = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{d_start}/{d_end}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        
        w_res = requests.get(url).json()
        w_rows = []
        for d in w_res['days']:
            for hr in d['hours']:
                w_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3),
                    'CloudCover': hr.get('cloudcover', 0), 
                    'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0), 
                    'PrecipProb': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_rows)
        print(f"✅ Погода отримана.")
    except Exception as e:
        print(f"❌ Помилка метео: {e}")

    # --- 4. ОБ'ЄДНАННЯ ТА РОТАЦІЯ (КОВЗНЕ ВІКНО) ---
    print("🔄 Оновлення та ротація бази...")
    
    # Збираємо нові дані
    df_new = df_w.copy() if not df_w.empty else pd.DataFrame(columns=['Time'])
    if fact_data_list:
        df_facts = pd.concat(fact_data_list).drop_duplicates('Time', keep='last')
        if not df_new.empty:
            df_new = pd.merge(df_new, df_facts, on='Time', how='left', suffixes=('', '_new'))
            if 'Fact_MW_new' in df_new.columns:
                df_new['Fact_MW'] = df_new['Fact_MW_new']
                df_new = df_new.drop(columns=['Fact_MW_new'])
        else:
            df_new = df_facts

    # Об'єднуємо зі старою базою
    df_final = pd.concat([df_main, df_new], ignore_index=True)
    
    # Видаляємо дублікати годин (залишаємо той рядок, де є Факт)
    df_final = df_final.sort_values(by=['Time', 'Fact_MW'], na_position='first')
    df_final = df_final.drop_duplicates(subset=['Time'], keep='last')
    
    # Сортуємо від старого до нового
    df_final = df_final.sort_values('Time').reset_index(drop=True)

    # ЗАСТОСУВАННЯ ЛІМІТУ (30 днів)
    if len(df_final) > LIMIT:
        print(f"🧹 Ротація: видаляємо {len(df_final) - LIMIT} найстаріших годин.")
        df_final = df_final.tail(LIMIT)

    # Збереження
    cols = ['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    df_final[cols].to_csv(BASE_FILE, index=False)
    
    print(f"💾 ФІНІШ: База актуальна. Рядків: {len(df_final)} (повні {DAYS_TO_KEEP} днів).")

if __name__ == "__main__":
    main()
