import imaplib, email, os, io, re
import pandas as pd
from github import Github
from datetime import datetime

# --- НАЛАШТУВАННЯ (Беруться з Secrets GitHub) ---
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASS = os.environ.get('EMAIL_PASS')
GH_TOKEN = os.environ.get('GH_TOKEN')
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"
CSV_PATH = "solar_ai_base.csv"

def parse_industrial_value(val):
    """Перетворює '10 846, 320' у число 10.84632 (МВт)"""
    if pd.isna(val) or val == "": return 0.0
    # Прибираємо пробіли, міняємо кому на крапку
    s = str(val).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        # Ділимо на 1000, бо в звіті кВт, а нам потрібні МВт
        return float(s) / 1000
    except: return 0.0

def get_data_from_mail():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Шукаємо листи з вашим звітом
        result, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        ids = data[0].split()
        
        new_rows = []
        # Перевіряємо останні 10 листів, щоб "закрити" дирку з 12.03
        for e_id in ids[-10:]:
            _, msg_data = mail.fetch(e_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            
            for part in msg.walk():
                fname = part.get_filename()
                if fname and "reportCEC" in fname:
                    print(f"📦 Знайдено звіт: {fname}")
                    # Читаємо Excel, пропускаючи перші 2 рядки шапки
                    df = pd.read_excel(io.BytesIO(part.get_payload(decode=True)), skiprows=2)
                    
                    # Нам потрібні колонки: 0 (Час) та 5 (Виробництво інвертором)
                    df = df.iloc[:, [0, 5]].dropna()
                    df.columns = ['Time', 'Fact_MW']
                    
                    # Чистимо дані
                    df['Fact_MW'] = df['Fact_MW'].apply(parse_industrial_value)
                    
                    # Важливо: приводимо дату до формату CSV (YYYY-MM-DD HH:00:00)
                    df['Time'] = pd.to_datetime(df['Time']).dt.strftime('%Y-%m-%d %H:00:00')
                    new_rows.append(df)
        
        mail.logout()
        return pd.concat(new_rows).drop_duplicates('Time') if new_rows else None
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")
        return None

# --- ОСНОВНИЙ ЦИКЛ ОНОВЛЕННЯ ---
new_data = get_data_from_mail()

if new_data is not None:
    g = Github(GH_TOKEN)
    repo = g.get_repo(REPO_NAME)
    contents = repo.get_contents(CSV_PATH)
    
    # Завантажуємо стару базу
    old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
    
    # Зливаємо докупи, пріоритет новим даним
    final_df = pd.concat([old_df, new_data]).drop_duplicates('Time', keep='last')
    final_df = final_df.sort_values('Time')
    
    # Оновлюємо на GitHub
    repo.update_file(
        contents.path, 
        f"Auto-update: {datetime.now().strftime('%d.%m %H:%M')}", 
        final_df.to_csv(index=False), 
        contents.sha
    )
    print("🚀 Базу успішно оновлено новими даними!")
else:
    print("💤 Нових звітів не знайдено.")
