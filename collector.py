import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # --- 1. ЗАВАНТАЖЕННЯ БАЗИ ---
    if os.path.exists(BASE_FILE):
        df_main = pd.read_csv(BASE_FILE)
        df_main['Time'] = pd.to_datetime(df_main['Time'])
        print(f"📋 База завантажена. Рядки: {len(df_main)}. Останній запис: {df_main['Time'].max()}")
    else:
        print("⚠️ База не знайдена, створюємо нову.")
        df_main = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # --- 2. ПОШТА (АСКОЕ) ---
    fact_data_list = []
    try:
        print("🔐 Підключення до пошти...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        
        # Беремо останні 50 листів (найнадійніший спосіб знайти нові листи)
        _, data = mail.search(None, 'ALL')
        msg_ids = data[0].split()
        last_ids = msg_ids[-50:]
        
        print(f"📩 Перевірка останніх {len(last_ids)} листів...")

        for num in last_ids:
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            
            # Фільтр по даті (лише за останні 7 днів)
            date_str = msg.get("Date")
            msg_date = email.utils.parsedate_to_datetime(date_str).replace(tzinfo=None)
            
            if msg_date > (datetime.now() - timedelta(days=7)):
                subject = msg.get("Subject")
                
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart': continue
                    filename = part.get_filename()
                    
                    if filename and (filename.endswith(".xlsx") or filename.endswith(".xls")):
                        print(f"📎 Файл: {filename} (Тема: {subject})")
                        try:
                            content = part.get_payload(decode=True)
                            # Читаємо Excel без заголовків (header=None) для ручного парсингу
                            df_excel = pd.read_excel(io.BytesIO(content), header=None)
                            
                            if not df_excel.empty:
                                # ОЧИЩЕННЯ: перетворюємо все в текст і міняємо коми на крапки
                                df_excel = df_excel.astype(str).replace({',': '.'}, regex=True)
                                
                                temp_rows = []
                                for _, row in df_excel.iterrows():
                                    # Намагаємося знайти Час у 1-й колонці та Число у 2-й
                                    t = pd.to_datetime(row[0], errors='coerce')
                                    f = pd.to_numeric(row[1], errors='coerce')
                                    
                                    if not pd.isna(t) and not pd.isna(f):
                                        temp_rows.append({'Time': t, 'Fact_MW': f})
                                
                                if temp_rows:
                                    fact_data_list.append(pd.DataFrame(temp_rows))
                                    print(f"✅ Додано {len(temp_rows)} рядків")
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
        print(f"✅ Погода отримана: {len(df_w)} рядків")
    except Exception as e:
        print(f"❌ Помилка метео: {e}")

    # --- 4. ОБ'ЄДНАННЯ ТА ЗБЕРЕЖЕННЯ ---
    print("🔄 Синхронізація...")
    
    # Збираємо нові дані (Погода + Факт)
    df_new = df_w.copy() if not df_w.empty else pd.DataFrame(columns=['Time'])
    
    if fact_data_list:
        df_facts = pd.concat(fact_data_list).drop_duplicates('Time', keep='last')
        if not df_new.empty:
            # Об'єднуємо погоду з фактом по часу
            df_new = pd.merge(df_new, df_facts, on='Time', how='left', suffixes=('', '_new'))
            if 'Fact_MW_new' in df_new.columns:
                df_new['Fact_MW'] = df_new['Fact_MW_new']
                df_new = df_new.drop(columns=['Fact_MW_new'])
        else:
            df_new = df_facts

    # Додаємо нове до старої бази
    df_final = pd.concat([df_main, df_new], ignore_index=True)
    
    # Розумне видалення дублікатів:
    # Спочатку сортуємо так, щоб рядки з Fact_MW були внизу
    df_final = df_final.sort_values(by=['Time', 'Fact_MW'], na_position='first')
    # Залишаємо останній запис для кожної години (той, що з фактом або найсвіжіший)
    df_final = df_final.drop_duplicates(subset=['Time'], keep='last')
    
    df_final = df_final.sort_values('Time').reset_index(drop=True)

    # Фінальний фільтр: залишаємо лише колонки бази
    cols = ['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    df_final = df_final[cols]

    df_final.to_csv(BASE_FILE, index=False)
    print(f"💾 ФІНІШ: База оновлена. Разом рядків: {len(df_final)}")

if __name__ == "__main__":
    main()
