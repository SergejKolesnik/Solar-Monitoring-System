import imaplib, email, os, io, re
import pandas as pd
from github import Github

# --- НАЛАШТУВАННЯ ---
EMAIL_USER = os.environ.get('EMAIL_USER')
EMAIL_PASS = os.environ.get('EMAIL_PASS')
GH_TOKEN = os.environ.get('GH_TOKEN')
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"

def run_diagnostic():
    try:
        print("🔗 Підключення до пошти...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        _, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        ids = data[0].split()
        
        if not ids:
            print("❌ Листів не знайдено!"); return

        res, msg_data = mail.fetch(ids[-1], "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        for part in msg.walk():
            fname = part.get_filename()
            if fname and "report" in fname:
                print(f"📦 ДІАГНОСТИКА ФАЙЛУ: {fname}")
                content = part.get_payload(decode=True)
                raw_df = pd.read_excel(io.BytesIO(content), header=None)
                
                print("\n--- СИРІ ДАНІ (ПЕРШІ 15 РЯДКІВ) ---")
                # Це надрукує таблицю прямо в лог GitHub
                print(raw_df.head(15).to_string()) 
                print("----------------------------------\n")
                
                # Перевірка типів даних у колонці з числами
                sample_val = raw_df.iloc[10, 5] if len(raw_df) > 10 else "N/A"
                print(f"Зразок значення в 5-й колонці: '{sample_val}' Type: {type(sample_val)}")
        
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка: {e}")

if __name__ == "__main__":
    run_diagnostic()
