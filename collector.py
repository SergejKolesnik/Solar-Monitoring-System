import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

# НАЛАШТУВАННЯ
BASE_FILE = "solar_ai_base.csv"
DAYS_TO_KEEP = 30 
LIMIT = DAYS_TO_KEEP * 24 

def main():
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖЕННЯ БАЗИ
    if os.path.exists(BASE_FILE):
        df_main = pd.read_csv(BASE_FILE)
        df_main['Time'] = pd.to_datetime(df_main['Time']).dt.floor('h')
        print(f"📋 База завантажена. Останній запис: {df_main['Time'].max()}")
    else:
        df_main = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ПОШТА (АСКОЕ)
    fact_data_list = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        _, data = mail.search(None, 'ALL')
        # Беремо останні 100 листів, щоб точно закрити дірки в датах
        last_ids = data[0].split()[-100:]
        
        print(f"📩 Аналізую останні {len(last_ids)} листів...")

        for num in last_ids:
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            msg_date = email.utils.parsedate_to_datetime(msg.get("Date")).replace(tzinfo=None)
            
            # Шукаємо звіти за останні 10 днів
            if msg_date > (datetime.now() - timedelta(days=10)):
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart': continue
                    filename = part.get_filename()
                    if filename and (filename.endswith(".xlsx") or filename.endswith(".xls")):
                        try:
                            content = part.get_payload(decode=True)
                            # Читаємо файл повністю
                            df_excel = pd.read_excel(io.BytesIO(content), header=None)
                            
                            # ДИНАМІЧНИЙ ПОШУК КОЛОНКИ ГЕНЕРАЦІЇ
                            # Шукаємо в 2-му рядку ключові слова
                            target_col = 5 # Стандарт для вашого звіту
                            for col_idx in range(len(df_excel.columns)):
                                cell_val = str(df_excel.iloc[1, col_idx]).lower()
                                if 'вироб' in cell_val or 'інвертор' in cell_val:
                                    target_col = col_idx
                                    break
                            
                            current_file_count = 0
                            for i in range(2, len(df_excel)):
                                row = df_excel.iloc[i]
                                # Розпізнаємо час
                                t = pd.to_datetime(row[0], errors='coerce')
                                if pd.isna(t): continue
                                
                                # Беремо значення генерації, чистимо від ком та пробілів
                                raw_val = str(row[target_col]).replace(',', '.').replace(' ', '')
                                f = pd.to_numeric(raw_val, errors='coerce')
                                
                                # Записуємо, навіть якщо там 0 або дуже мале число (вечір)
                                if not pd.isna(f):
                                    fact_data_list.append({'Time': t.floor('h'), 'Fact_MW': f})
                                    current_file_count += 1
                            
                            if current_file_count > 0:
                                print(f"✅ Оброблено {filename}: +{current_file_count} записів")
                                
                        except Exception as ex:
                            print(f"❌ Помилка в {filename}: {ex}")
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")

    # 3. ПОГОДА (Visual Crossing)
    df_w = pd.DataFrame()
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        # Беремо ширший діапазон для синхронізації
        d_start = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        d_end = (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{d_start}/{d_end}?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        
        w_res = requests.get(url).json()
        w_rows = []
        for d in w_res['days']:
            for hr in d['hours']:
                w_rows.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}").floor('h'),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3),
                    'CloudCover': hr.get('cloudcover', 0), 
                    'Temp': hr.get('temp', 0),
                    'WindSpeed': hr.get('windspeed', 0), 
                    'PrecipProb': hr.get('precipprob', 0)
                })
        df_w = pd.DataFrame(w_rows)
    except Exception as e:
        print(f"❌ Помилка метео: {e}")

    # 4. ОБ'ЄДНАННЯ ТА РОТАЦІЯ (30 ДНІВ)
    df_new_facts = pd.DataFrame(fact_data_list)
    if not df_new_facts.empty:
        df_new_facts = df_new_facts.drop_duplicates('Time', keep='last')

    # Конкатенація та вибір кращих значень (де є Fact_MW)
    df_final = pd.concat([df_main, df_w, df_new_facts], ignore_index=True)
    df_final = df_final.sort_values(by=['Time', 'Fact_MW'], na_position='first')
    df_final = df_final.drop_duplicates(subset=['Time'], keep='last')
    
    # Сортування та обрізка до 30 днів (720 годин)
    df_final = df_final.sort_values('Time').tail(LIMIT)

    # Збереження
    df_final[['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']].to_csv(BASE_FILE, index=False)
    
    last_f = df_final.dropna(subset=['Fact_MW'])['Time'].max()
    print(f"💾 ФІНІШ: Останній факт у базі: {last_f}")

if __name__ == "__main__":
    main()
