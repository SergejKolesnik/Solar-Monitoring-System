import imaplib, email, os, io, sys
import pandas as pd
from github import Github

# Налаштування кодування для виводу в лог
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- ПРЯМЕ ПРИЗНАЧЕННЯ ЗМІННИХ ---
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
GH_TOKEN = os.getenv('GH_TOKEN')

def run_diagnostic():
    try:
        print(f"🔗 Спроба підключення для: {EMAIL_USER}...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        print("✅ Вхід у пошту успішний!")
        
        mail.select("inbox")
        # Шукаємо листи (використовуємо інший метод пошуку для надійності)
        result, data = mail.uid('search', None, '(SUBJECT "Звіт про роботу установ")')
        uids = data[0].split()
        
        if not uids:
            print("📭 Листів з такою темою не знайдено."); return

        # Беремо останній знайдений лист за UID
        res, msg_data = mail.uid('fetch', uids[-1], "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        for part in msg.walk():
            fname = part.get_filename()
            if fname and "report" in fname:
                print(f"📦 ФАЙЛ ЗНАЙДЕНО: {fname}")
                content = part.get_payload(decode=True)
                raw_df = pd.read_excel(io.BytesIO(content), header=None)
                
                print("\n--- СИРІ ДАНІ (ПЕРШІ 15 РЯДКІВ) ---")
                # Виводимо перші 15 рядків, щоб точно побачити структуру
                print(raw_df.head(15).to_string()) 
                print("----------------------------------\n")
        
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка: {str(e)}")

if __name__ == "__main__":
    run_diagnostic()
