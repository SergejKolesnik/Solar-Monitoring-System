import imaplib, email, os, io, re
import pandas as pd
from github import Github

# --- ПРЯМЕ ПРИЗНАЧЕННЯ ЗМІННИХ ---
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')
GH_TOKEN = os.getenv('GH_TOKEN') or os.getenv('GH_TOKEN_SOLAR') # Перевірка обох варіантів назви

def run_diagnostic():
    try:
        if not EMAIL_USER or not EMAIL_PASS:
            print("❌ ПОМИЛКА: Секрети EMAIL_USER або EMAIL_PASS не знайдені в GitHub Settings!")
            return

        print(f"🔗 Спроба підключення для: {EMAIL_USER}...")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        
        # Спроба входу
        mail.login(EMAIL_USER, EMAIL_PASS)
        print("✅ Вхід у пошту успішний!")
        
        mail.select("inbox")
        _, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        ids = data[0].split()
        
        if not ids:
            print("📭 Листів з темою 'Звіт про роботу установ' не знайдено."); return

        res, msg_data = mail.fetch(ids[-1], "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        
        for part in msg.walk():
            fname = part.get_filename()
            if fname and "report" in fname:
                print(f"📦 ФАЙЛ ЗНАЙДЕНО: {fname}")
                content = part.get_payload(decode=True)
                raw_df = pd.read_excel(io.BytesIO(content), header=None)
                
                print("\n--- СИРІ ДАНІ (ПЕРШІ 15 РЯДКІВ) ---")
                print(raw_df.head(15).to_string()) 
                print("----------------------------------\n")
        
        mail.logout()
    except Exception as e:
        print(f"❌ Помилка: {e}")

if __name__ == "__main__":
    run_diagnostic()
