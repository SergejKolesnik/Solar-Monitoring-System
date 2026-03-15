import imaplib, email, os, io, sys, re
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
    """Очищення промислового формату: '10 846,320' -> 10.84632"""
    if pd.isna(val) or val == "": return 0.0
    # Видаляємо все крім цифр та роздільників
    s = re.sub(r'[^\d,.]', '', str(val)).replace(',', '.')
    try:
        return float(s) / 1000  # кВт -> МВт
    except: return 0.0

def run_sync():
    try:
        print(f"Connecting to {EMAIL_USER}...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Пошук за темою
        _, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        uids = data[0].split()
        
        if not uids:
            print("No emails found."); return

        all_dfs = []
        # Перевіряємо останні 10 листів, щоб закрити всі пропуски
        for uid in uids[-10:]:
            _, msg_data = mail.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                fname = part.get_filename()
                if fname and "report" in fname:
                    print(f"Processing: {fname}")
                    raw_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                    
                    # Шукаємо початок даних (рядок з датою)
                    start_idx = None
                    for i, row in raw_df.iterrows():
                        if re.search(r'\d{4}-\d{2}-\d{2}', str(row[0])):
                            start_idx = i
                            break
                    
                    if start_idx is not None:
                        df = raw_df.iloc[start_idx:].copy()
                        # Стовпець 0 - Час, Стовпець 5 - Виробництво
                        df = df.iloc[:, [0, 5]].dropna()
                        df.columns = ['Time', 'Fact_MW']
                        df['Fact_MW'] = df['Fact_MW'].apply(clean_num)
                        df['Time'] = pd.to_datetime(df['Time']).dt.strftime('%Y-%m-%d %H:00:00')
                        all_dfs.append(df)
        
        mail.logout()
        
        if all_dfs:
            new_combined = pd.concat(all_dfs).drop_duplicates('Time')
            print(f"Extracted {len(new_combined)} rows.")
            
            # GitHub Update
            g = Github(GH_TOKEN)
            repo = g.get_repo(REPO_NAME)
            contents = repo.get_contents(CSV_PATH)
            old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
            
            # Об'єднуємо, залишаємо новіші дані при дублікатах
            final_df = pd.concat([old_df, new_combined]).drop_duplicates('Time', keep='last')
            final_df['Time'] = pd.to_datetime(final_df['Time'])
            final_df = final_df.sort_values('Time')
            
            # Запис
            repo.update_file(contents.path, f"AI Sync: {datetime.now().strftime('%d.%m %H:%M')}", 
                             final_df.to_csv(index=False), contents.sha)
            print("DONE: CSV UPDATED ON GITHUB!")
        else:
            print("No valid data found in files.")

    except Exception as e:
        # Виводимо помилку англійською, щоб уникнути проблем з ASCII
        print(f"ERROR: {str(e)}")

if __name__ == "__main__":
    run_sync()
