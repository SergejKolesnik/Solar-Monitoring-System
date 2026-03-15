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

def clean_value(val):
    """Очищення промислового формату: '10 846, 320' -> 10.84632"""
    if pd.isna(val) or val == "": return 0.0
    # Прибираємо нерозривні пробіли, звичайні пробіли та міняємо кому на крапку
    s = str(val).replace('\xa0', '').replace(' ', '').replace(',', '.')
    try:
        return float(s) / 1000  # кВт -> МВт
    except: return 0.0

def run_sync():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        _, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        ids = data[0].split()
        
        all_new_data = []
        for e_id in ids[-10:]:
            _, m_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(m_data[0][1])
            for part in msg.walk():
                fname = part.get_filename()
                if fname and "reportCEC" in fname:
                    print(f"📦 Аналізую файл: {fname}")
                    raw_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                    
                    # Динамічно шукаємо рядок, де починаються дані (шукаємо дату)
                    data_start_idx = None
                    for idx, row in raw_df.iterrows():
                        if re.search(r'\d{4}-\d{2}-\d{2}', str(row[0])):
                            data_start_idx = idx
                            break
                    
                    if data_start_idx is not None:
                        # Беремо дані з цього рядка до кінця
                        df = raw_df.iloc[data_start_idx:].copy()
                        # Стовпець 0 - Час, Стовпець 5 - Виробництво (стовпець F)
                        df = df.iloc[:, [0, 5]].dropna()
                        df.columns = ['Time', 'Fact_MW']
                        
                        df['Fact_MW'] = df['Fact_MW'].apply(clean_value)
                        df['Time'] = pd.to_datetime(df['Time']).dt.strftime('%Y-%m-%d %H:00:00')
                        
                        print(f"✅ Успішно витягнуто {len(df)} рядків.")
                        all_new_data.append(df)
        
        mail.logout()
        
        if not all_new_data:
            print("📭 Нових звітів не виявлено."); return

        new_df = pd.concat(all_new_data).drop_duplicates('Time')
        
        # GitHub Logic
        g = Github(GH_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(CSV_PATH)
        old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
        
        # Зшиваємо базу
        final_df = pd.concat([old_df, new_df]).drop_duplicates('Time', keep='last')
        final_df['Time'] = pd.to_datetime(final_df['Time'])
        final_df = final_df.sort_values('Time')
        
        repo.update_file(contents.path, f"AI Sync: {datetime.now().strftime('%d.%m %H:%M')}", 
                         final_df.to_csv(index=False), contents.sha)
        print("🚀 База на GitHub оновлена!")

    except Exception as e:
        print(f"❌ Помилка виконання: {e}")

if __name__ == "__main__":
    run_sync()
