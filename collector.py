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
    """Перетворює текст '10 846,320' у число 10.84632"""
    if pd.isna(val) or val == "": return 0.0
    # Видаляємо все крім цифр, ком та крапок
    s = re.sub(r'[^\d,.]', '', str(val)).replace(',', '.')
    try:
        return float(s) / 1000  # кВт -> МВт
    except: return 0.0

def run_sync():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Шукаємо листи зі звітом
        _, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        ids = data[0].split()
        
        all_dfs = []
        for e_id in ids[-10:]: # перевіряємо останні 10 листів
            _, m_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(m_data[0][1])
            for part in msg.walk():
                fname = part.get_filename()
                if fname and "reportCEC" in fname:
                    print(f"📦 Обробляю: {fname}")
                    # Читаємо файл повністю
                    raw_df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), header=None)
                    
                    # Шукаємо рядок з датою (початок даних)
                    start_idx = None
                    for i, row in raw_df.iterrows():
                        if re.search(r'\d{4}-\d{2}-\d{2}', str(row[0])):
                            start_idx = i
                            break
                    
                    if start_idx is not None:
                        df = raw_df.iloc[start_idx:].copy()
                        # Стовпець 0 - Час, Стовпець 5 - Виробництво (стовпець F)
                        df = df.iloc[:, [0, 5]].dropna()
                        df.columns = ['Time', 'Fact_MW']
                        df['Fact_MW'] = df['Fact_MW'].apply(clean_industrial_num)
                        df['Time'] = pd.to_datetime(df['Time']).dt.strftime('%Y-%m-%d %H:00:00')
                        all_dfs.append(df)
        
        mail.logout()
        if not all_dfs: return

        new_combined = pd.concat(all_dfs).drop_duplicates('Time')
        
        # GitHub Update
        g = Github(GH_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(CSV_PATH)
        old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
        
        final_df = pd.concat([old_df, new_combined]).drop_duplicates('Time', keep='last')
        final_df['Time'] = pd.to_datetime(final_df['Time'])
        final_df = final_df.sort_values('Time')
        
        repo.update_file(contents.path, f"AI Update: {datetime.now().strftime('%d.%m %H:%M')}", 
                         final_df.to_csv(index=False), contents.sha)
        print("🚀 Успіх! База на GitHub оновлена.")

    except Exception as e:
        print(f"❌ Помилка: {e}")

if __name__ == "__main__":
    run_sync()
