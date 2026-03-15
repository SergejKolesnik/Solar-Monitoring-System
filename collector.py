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
    """Очищає текст звіту: '10 846, 320' -> 10.84632"""
    if pd.isna(val) or val == "": return 0.0
    s = str(val).replace(" ", "").replace(",", ".")
    try:
        # Якщо в звіті кВт-год, ділимо на 1000 для отримання МВт-год
        return float(s) / 1000 
    except: return 0.0

def process_emails():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Шукаємо звіти
        _, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        ids = data[0].split()
        all_dfs = []

        for e_id in ids[-10:]: # Останні 10 листів
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            for part in msg.walk():
                fname = part.get_filename()
                if fname and "reportCEC" in fname:
                    df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), skiprows=2)
                    # Беремо першу колонку (Час) та останню (Вироб. інвертором)
                    df = df.iloc[:, [0, 5]].dropna()
                    df.columns = ['Time', 'Fact_MW']
                    df['Fact_MW'] = df['Fact_MW'].apply(clean_value)
                    all_dfs.append(df)
        mail.logout()
        return pd.concat(all_dfs).drop_duplicates('Time') if all_dfs else None
    except Exception as e:
        print(f"Помилка: {e}"); return None

# Логіка оновлення GitHub
new_data = process_emails()
if new_data is not None:
    g = Github(GH_TOKEN)
    repo = g.get_repo(REPO_NAME)
    contents = repo.get_contents(CSV_PATH)
    old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
    final_df = pd.concat([old_df, new_data]).drop_duplicates('Time', keep='last')
    final_df['Time'] = pd.to_datetime(final_df['Time'])
    final_df = final_df.sort_values('Time')
    repo.update_file(contents.path, "AI Base Auto-Update", final_df.to_csv(index=False), contents.sha)
    print("✅ Дані оновлено успішно!")
