import pandas as pd
import requests
import os
import imaplib
import email
import io
from datetime import datetime, timedelta

BASE_FILE = "solar_ai_base.csv"

def main():
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1. ЗАВАНТАЖУЄМО ТЕ, ЩО Є (або створюємо порожній)
    if os.path.exists(BASE_FILE):
        df = pd.read_csv(BASE_FILE)
        df['Time'] = pd.to_datetime(df['Time'])
    else:
        df = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    # 2. ПРЯМЕ ЧИТАННЯ ПОШТИ (АСКОЕ)
    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")
        # Беремо останні 50 листів без складних фільтрів
        _, data = mail.search(None, 'ALL')
        for num in data[0].split()[-50:]:
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                if part.get_filename() and (part.get_filename().endswith(".xlsx") or part.get_filename().endswith(".xls")):
                    excel_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                    # Беремо 1-шу колонку (час) і 6-ту (генерація)
                    for i in range(2, len(excel_df)):
                        t = pd.to_datetime(excel_df.iloc[i, 0], errors='coerce')
                        f = pd.to_numeric(str(excel_df.iloc[i, 5]).replace(',', '.'), errors='coerce')
                        if not pd.isna(t) and not pd.isna(f):
                            # ОКРУГЛЮЄМО ДО ГОДИНИ - це критично для склейки!
                            new_facts.append({'Time': t.replace(minute=0, second=0, microsecond=0), 'Fact_MW': f})
        mail.logout()
    except Exception as e: print(f"⚠️ Помилка пошти: {e}")

    if new_facts:
        df_new_gen = pd.DataFrame(new_facts).drop_duplicates('Time')
        # Об'єднуємо факти
        df = pd.merge(df, df_new_gen, on='Time', how='outer', suffixes=('', '_new'))
        if 'Fact_MW_new' in df.columns:
            df['Fact_MW'] = df['Fact_MW_new'].combine_first(df['Fact_MW'])
            df = df.drop(columns=['Fact_MW_new'])

    # 3. ДОДАЄМО ПОГОДУ (не видаляючи факти!)
    try:
        api_key = os.getenv('WEATHER_API_KEY')
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/{(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}/{(datetime.now()+timedelta(days=3)).strftime('%Y-%m-%d')}?unitGroup=metric&key={api_key}&contentType=json"
        w_res = requests.get(url).json()
        for day in w_res['days']:
            for hr in day['hours']:
                dt = pd.to_datetime(f"{day['datetime']} {hr['datetime']}")
                # Якщо такого часу в базі немає - додаємо рядок
                if dt not in df['Time'].values:
                    df = pd.concat([df, pd.DataFrame([{'Time': dt}])], ignore_index=True)
                
                # Оновлюємо погодні колонки
                mask = df['Time'] == dt
                df.loc[mask, 'Forecast_MW'] = round(hr.get('solarradiation', 0) * 0.0114, 3)
                df.loc[mask, 'CloudCover'] = hr.get('cloudcover', 0)
                df.loc[mask, 'Temp'] = hr.get('temp', 0)
        print("✅ Погода оновлена")
    except Exception as e: print(f"⚠️ Помилка погоди: {e}")

    # 4. ЗБЕРЕЖЕННЯ
    df = df.sort_values('Time').drop_duplicates('Time').tail(800)
    df.to_csv(BASE_FILE, index=False)
    print(f"💾 ФІНІШ. Рядків: {len(df)}. Остання дата: {df['Time'].max()}")

if __name__ == "__main__":
    main()
