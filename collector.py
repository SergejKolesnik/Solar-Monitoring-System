import os
import requests
import pandas as pd
import imaplib
import email
from email.header import decode_header
import io
from datetime import datetime, timedelta
import pytz

# 1. КОНФІГУРАЦІЯ
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
CSV_FILE = "solar_ai_base.csv"
LAT, LON = "47.56", "34.39"
UA_TZ = pytz.timezone('Europe/Kyiv')

def get_forecast():
    try:
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{LAT},{LON}/next3days?unitGroup=metric&elements=datetime,solarradiation&key={WEATHER_API_KEY}&contentType=json"
        res = requests.get(url, timeout=15).json()
        forecast_list = []
        for day in res['days']:
            for hr in day['hours']:
                forecast_list.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Forecast_MW': round(hr.get('solarradiation', 0) * 11.4 * 0.001, 3)
                })
        return pd.DataFrame(forecast_list)
    except Exception as e:
        print(f"Помилка погоди: {e}")
        return pd.DataFrame()

def get_fact_from_mail():
    askoe_records = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        date_cut = (datetime.now(UA_TZ) - timedelta(days=3)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_cut}" SUBJECT "ASKOE")')
        
        for num in data[0].split():
            _, msg_data = mail.fetch(num, '(RFC822)')
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith('.xlsx') or part.get_filename().endswith('.csv')):
                    payload = part.get_payload(decode=True)
                    df_mail = pd.read_excel(io.BytesIO(payload)) if part.get_filename().endswith('.xlsx') else pd.read_csv(io.BytesIO(payload))
                    for _, row in df_mail.iterrows():
                        askoe_records.append({
                            'Time': pd.to_datetime(row.iloc[0]),
                            'Fact_MW': round(float(row.iloc[1]), 3)
                        })
        mail.logout()
        return pd.DataFrame(askoe_records)
    except Exception as e:
        print(f"Помилка пошти: {e}")
        return pd.DataFrame()

def sync_all():
    # Завантажуємо базу
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # 1. ОБРОБКА ПРОГНОЗУ (Тільки нові записи!)
    df_f = get_forecast()
    if not df_f.empty:
        # Фільтруємо ТІЛЬКИ ті години, яких ще взагалі немає в базі
        new_hours = df_f[~df_f['Time'].isin(df_base['Time'])]
        if not new_hours.empty:
            df_base = pd.concat([df_base, new_hours], ignore_index=True)
            print(f"Додано {len(new_hours)} нових годин з прогнозом.")
        else:
            print("Нових годин для прогнозу не знайдено. Старі прогнози не переписуємо.")

    # 2. ОБРОБКА ФАКТУ (Оновлюємо існуючі записи)
    df_fact = get_fact_from_mail()
    if not df_fact.empty:
        df_fact['Time'] = pd.to_datetime(df_fact['Time'])
        for _, row in df_fact.iterrows():
            # Шукаємо рядок з таким часом і вписуємо факт, якщо його ще немає
            mask = df_base['Time'] == row['Time']
            if mask.any():
                # Перевіряємо, чи факт порожній або відрізняється (щоб не терти дані)
                df_base.loc[mask, 'Fact_MW'] = row['Fact_MW']
            else:
                # Якщо прогнозу чомусь не було, створюємо рядок тільки з фактом
                new_row = pd.DataFrame([row])
                df_base = pd.concat([df_base, new_row], ignore_index=True)
        print(f"Оновлено дані факту з пошти.")

    # Зберігаємо
    df_base = df_base.sort_values('Time').drop_duplicates('Time', keep='first')
    df_base.to_csv(CSV_FILE, index=False)
    print("Синхронізація завершена успішно.")

if __name__ == "__main__":
    sync_all()
