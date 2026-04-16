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
    print(f"🚀 СТАРТ РОБОТИ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # --- 1. ЗАВАНТАЖЕННЯ ІСНУЮЧОЇ БАЗИ ---
    if os.path.exists(BASE_FILE):
        df_main = pd.read_csv(BASE_FILE)
        df_main['Time'] = pd.to_datetime(df_main['Time'])
        print(f"📋 База завантажена. Рядки: {len(df_main)}. Останній запис: {df_main['Time'].max()}")
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
        
        # Шукаємо за останні 7 днів, щоб точно нічого не пропустити
        date_cut = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
        _, messages = mail.search(None, f'(SINCE {date_cut})')
        
        msg_ids = messages[0].split()
        print(f"📩 Знайдено листів за період з {date_cut}: {len(msg_ids)}")

        for num in msg_ids:
            _, data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            subject = msg.get("Subject")
            
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart': continue
                if part.get('Content-Disposition') is None: continue
                
                filename = part.get_filename()
                if filename and (filename.endswith(".xlsx") or filename.endswith(".xls")):
                    print(f"📎 Обробка вкладення: {filename} (Тема: {subject})")
                    try:
                        content = part.get_payload(decode=True)
                        # Читаємо Excel (використовуємо io.BytesIO)
                        df_excel = pd.read_excel(io.BytesIO(content))
                        
                        # Тут ми припускаємо, що Excel має колонки 'Час' та 'Факт' 
                        # (Налаштуйте назви під ваш формат АСКОЕ, якщо вони відрізняються)
                        # Приклад для типового звіту:
                        if not df_excel.empty:
                            # Очищення та форматування даних з Excel
                            # (Замініть назви колонок на реальні з вашого файлу)
                            temp_df = pd.DataFrame({
                                'Time': pd.to_datetime(df_excel.iloc[:, 0]), # Перша колонка - час
                                'Fact_MW': df_excel.iloc[:, 1].astype(float) # Друга колонка - факт
                            })
                            fact_data_list.append(temp_df)
                            print(f"✅ Успішно вилучено {len(temp_df)} рядків факту")
                    except Exception as ex:
                        print(f"❌ Помилка читання Excel {filename}: {ex}")
        
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"❌ Критична помилка пошти: {e}")

    # --- 3. ПОГОДА (Visual Crossing) ---
    df_w = pd.DataFrame()
    try:
        print("☁️ Запит прогнозу погоди...")
        api_key = os.getenv('WEATHER_API_KEY')
        # Беремо історію за 3 дні та прогноз на 3 дні вперед
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
        print(f"✅ Отримано погодніх даних: {len(df_w)} рядків")
    except Exception as e:
        print(f"❌ Помилка метеосервісу: {e}")

    # --- 4. ОБ'ЄДНАННЯ ТА СИНХРОНІЗАЦІЯ ---
    print("🔄 Синхронізація даних...")
    
    # Створюємо датафрейм з нових даних
    df_new = df_w.copy() if not df_w.empty else pd.DataFrame(columns=['Time'])
    
    if fact_data_list:
        df_facts = pd.concat(fact_data_list).drop_duplicates('Time', keep='last')
        if not df_new.empty:
            df_new = pd.merge(df_new, df_facts, on='Time', how='left')
        else:
            df_new = df_facts

    # Об'єднуємо стару базу з новими даними
    # Важливо: використовуємо keep='last', щоб оновлювати прогноз на свіжіший
    df_final = pd.concat([df_main, df_new], ignore_index=True)
    
    # Видаляємо дублікати по часу, залишаючи останню версію (де є Факт)
    df_final = df_final.sort_values(by=['Time', 'Fact_MW'], na_position='first')
    df_final = df_final.drop_duplicates(subset=['Time'], keep='last')
    
    # Сортуємо по даті перед збереженням
    df_final = df_final.sort_values('Time').reset_index(drop=True)

    # Зберігаємо
    df_final.to_csv(BASE_FILE, index=False)
    print(f"💾 ФІНІШ: База оновлена. Разом рядків: {len(df_final)}")

if __name__ == "__main__":
    main()
