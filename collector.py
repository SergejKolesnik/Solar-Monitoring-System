import imaplib, email, os, io, sys, re
import pandas as pd
from github import Github
from datetime import datetime

# Налаштування української мови для логів
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- НАЛАШТУВАННЯ ---
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
GH_TOKEN = os.getenv('GH_TOKEN')
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"
CSV_PATH = "solar_ai_base.csv"

def clean_num(val):
    """Очищення: '10 846,320' -> 10.84632 (МВт)"""
    if pd.isna(val) or val == "": return 0.0
    s = re.sub(r'[^\d,.]', '', str(val)).replace(',', '.')
    try:
        return float(s) / 1000
    except: return 0.0

def run_sync():
    try:
        print(f"🔗 Підключення до: {EMAIL_USER}...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Шукаємо листи (тема "Звіт про роботу установ")
        _, data = mail.uid('search', None, '(SUBJECT "Звіт про роботу установ")')
        uids = data[0].split()
        
        if not uids:
            print("📭 Листів не знайдено."); return

        all_dfs = []
        for uid in uids[-10:]: # Перевіряємо останні 10 листів
            _, msg_data = mail.uid('fetch', uid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                fname = part.get_filename()
                if fname and "report" in fname:
                    print(f"📦 Обробляю файл: {fname}")
                    raw_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                    
                    # Шукаємо рядок з датою
                    start_idx = None
                    for i, row in raw_df.iterrows():
                        if re.search(r'\d{4}-\d{2}-\d{2}', str(row[0])):
                            start_idx = i
                            break
                    
                    if start_idx is not None:
                        df = raw_df.iloc[start_idx:].copy()
                        df = df.iloc[:, [0, 5]].dropna()
                        df.columns = ['Time', 'Fact_MW']
                        df['Fact_MW'] = df['Fact_MW'].apply(clean_num)
                        df['Time'] = pd.to_datetime(df['Time']).dt.strftime('%Y-%m-%d %H:00:00')
                        all_dfs.append(df)
        
        mail.logout()
        
        if all_dfs:
            new_combined = pd.concat(all_dfs).drop_duplicates('Time')
            print(f"✅ Знайдено {len(new_combined)} рядків нових даних.")
            
            # Оновлення GitHub
            g = Github(GH_TOKEN)
            repo = g.get_repo(REPO_NAME)
            contents = repo.get_contents(CSV_PATH)
            old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
            
            final_df = pd.concat([old_df, new_combined]).drop_duplicates('Time', keep='last')
            final_df['Time'] = pd.to_datetime(final_df['Time'])
            final_df = final_df.sort_values('Time')
            
            repo.update_file(contents.path, f"AI Sync: {datetime.now().strftime('%d.%m %H:%M')}", 
                             final_df.to_csv(index=False), contents.sha)
            print("🚀 БАЗУ УСПІШНО ОНОВЛЕНО НА GITHUB!")
        else:
            print("🤔 Дані у файлах не знайдено.")

    except Exception as e:
        print(f"❌ Помилка: {str(e)}")

if __name__ == "__main__":
    run_sync()
