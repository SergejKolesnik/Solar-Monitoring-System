import imaplib, email, os, io, re
import pandas as pd
from github import Github

# --- КОНФІГ ---
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
GH_TOKEN = os.getenv('GH_TOKEN')
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"
CSV_PATH = "solar_ai_base.csv"

def clean_num(val):
    try:
        s = re.sub(r'[^\d,.]', '', str(val)).replace(',', '.')
        return float(s) / 1000
    except: return 0.0

def run():
    try:
        # 1. ПОШТА
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("INBOX")
        
        # Шукаємо ВСІ листи від відправника (так надійніше, ніж за темою)
        _, data = mail.search(None, 'ALL')
        uids = data[0].split()
        
        all_dfs = []
        for uid in uids[-15:]: # Останні 15 листів
            _, msg_data = mail.fetch(uid, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                if part.get_content_maintype() == 'application':
                    # Завантажуємо вміст без перевірки назви (щоб уникнути ASCII error)
                    try:
                        df_raw = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                        # Шукаємо рядок з датою у першій колонці
                        for i, row in df_raw.iterrows():
                            if re.search(r'\d{4}-\d{2}-\d{2}', str(row[0])):
                                # Якщо знайшли дату, забираємо цей блок
                                temp_df = df_raw.iloc[i:].copy()
                                temp_df = temp_df.iloc[:, [0, 5]].dropna()
                                temp_df.columns = ['Time', 'Fact_MW']
                                temp_df['Fact_MW'] = temp_df['Fact_MW'].apply(clean_num)
                                temp_df['Time'] = pd.to_datetime(temp_df['Time']).dt.strftime('%Y-%m-%d %H:00:00')
                                all_dfs.append(temp_df)
                                break
                    except: continue
        mail.logout()

        if not all_dfs:
            print("No data found in recent emails.")
            return

        # 2. GITHUB
        new_data = pd.concat(all_dfs).drop_duplicates('Time')
        g = Github(GH_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(CSV_PATH)
        old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
        
        final_df = pd.concat([old_df, new_data]).drop_duplicates('Time', keep='last')
        final_df['Time'] = pd.to_datetime(final_df['Time'])
        final_df = final_df.sort_values('Time')
        
        repo.update_file(contents.path, "Update", final_df.to_csv(index=False), contents.sha)
        print("Done. Base updated.")

    except Exception as e:
        # Друкуємо тільки тип помилки без деталей, де може бути кирилиця
        print(f"Error type: {type(e).__name__}")

if __name__ == "__main__":
    run()
