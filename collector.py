import imaplib, email, os, io, re
import pandas as pd
from github import Github
from datetime import datetime

# --- НАЛАШТУВАННЯ ---
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
GH_TOKEN = os.getenv('GH_TOKEN')
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"
CSV_PATH = "solar_ai_base.csv"

def clean_num(val):
    if pd.isna(val) or val == "": return 0.0
    s = re.sub(r'[^\d,.]', '', str(val)).replace(',', '.')
    try:
        return float(s) / 1000
    except: return 0.0

def run_sync():
    try:
        # 1. ПІДКЛЮЧЕННЯ
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Шукаємо листи за темою (використовуємо UID для надійності)
        _, data = mail.uid('search', None, '(SUBJECT "Звіт про роботу установ")')
        uids = data[0].split()
        
        if not uids:
            mail.logout()
            return

        all_dfs = []
        # Перевіряємо останні 10 листів
        for uid in uids[-10:]:
            _, msg_data = mail.uid('fetch', uid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                # Перевіряємо вкладення без виводу назви в лог (щоб уникнути помилки ASCII)
                if part.get_content_maintype() == 'application' and 'report' in str(part.get_filename()).lower():
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
            
            # 2. ОНОВЛЕННЯ GITHUB
            g = Github(GH_TOKEN)
            repo = g.get_repo(REPO_NAME)
            contents = repo.get_contents(CSV_PATH)
            old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
            
            final_df = pd.concat([old_df, new_combined]).drop_duplicates('Time', keep='last')
            final_df['Time'] = pd.to_datetime(final_df['Time'])
            final_df = final_df.sort_values('Time')
            
            repo.update_file(
                contents.path, 
                "DB Update", 
                final_df.to_csv(index=False), 
                contents.sha
            )
            # Тільки один короткий напис для лога англійською
            print("SUCCESS: Database updated.")
        else:
            print("FAIL: No data found.")

    except Exception:
        # Якщо сталася помилка, ми її не друкуємо, щоб не "повісити" ASCII
        print("CRITICAL ERROR: Connection or Auth issue.")

if __name__ == "__main__":
    run_sync()
