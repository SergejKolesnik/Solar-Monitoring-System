import imaplib, email, os, io, re, time
import pandas as pd
from github import Github
from datetime import datetime

# --- НАЛАШТУВАННЯ ---
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASS = os.environ.get('EMAIL_PASS')
GH_TOKEN = os.environ.get('GH_TOKEN')
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"
CSV_PATH = "solar_ai_base.csv"

def clean_industrial_num(val):
    """Обробка чисел: '10 846, 320' -> 10.84632"""
    if pd.isna(val) or val == "": return 0.0
    # Видаляємо всі пробіли (включаючи нерозривні \xa0) та міняємо кому на крапку
    s = str(val).replace('\xa0', '').replace(' ', '').replace(',', '.')
    try:
        return float(s) / 1000 # Перевід кВт -> МВт
    except: return 0.0

def run_sync():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Пошук листів з темою "Звіт про роботу установ"
        _, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        ids = data[0].split()
        
        dfs = []
        for e_id in ids[-10:]: # Перевіряємо останні 10 звітів
            _, m_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(m_data[0][1])
            for part in msg.walk():
                fname = part.get_filename()
                if fname and "reportCEC" in fname:
                    print(f"🔎 Аналіз файлу: {fname}")
                    # Читаємо файл повністю, щоб знайти початок даних
                    raw_data = part.get_payload(decode=True)
                    full_df = pd.read_excel(io.BytesIO(raw_data))
                    
                    # Шукаємо рядок, де в першій колонці є дата
                    start_row = 0
                    for i, row in full_df.iterrows():
                        if re.search(r'\d{4}-\d{2}-\d{2}', str(row.iloc[0])):
                            start_row = i
                            break
                    
                    # Перезавантажуємо з правильного рядка
                    df = pd.read_excel(io.BytesIO(raw_data), skiprows=start_row)
                    # Нам потрібна 1-ша колонка (Час) та 6-та (Вироб. інвертором, індекс 5)
                    df = df.iloc[:, [0, 5]].dropna()
                    df.columns = ['Time', 'Fact_MW']
                    
                    df['Fact_MW'] = df['Fact_MW'].apply(clean_industrial_num)
                    # Форматуємо час до годин
                    df['Time'] = pd.to_datetime(df['Time']).dt.strftime('%Y-%m-%d %H:00:00')
                    
                    print(f"✅ Знайдено {len(df)} рядків даних.")
                    dfs.append(df)
        
        mail.logout()
        
        if not dfs:
            print("📭 Нових даних reportCEC не знайдено."); return

        new_combined = pd.concat(dfs).drop_duplicates('Time')
        
        # Оновлення на GitHub
        g = Github(GH_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(CSV_PATH)
        old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
        
        # З'єднуємо стару базу з новою
        final_df = pd.concat([old_df, new_combined]).drop_duplicates('Time', keep='last')
        final_df['Time'] = pd.to_datetime(final_df['Time'])
        final_df = final_df.sort_values('Time')
        
        repo.update_file(contents.path, f"AI Sync: {datetime.now().strftime('%d.%m %H:%M')}", 
                         final_df.to_csv(index=False), contents.sha)
        print("🚀 GitHub CSV успішно оновлено!")

    except Exception as e:
        print(f"❌ Критична помилка: {e}")

if __name__ == "__main__":
    run_sync()
