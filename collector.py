import imaplib
import email
import pandas as pd
import requests
import base64
import os
from io import BytesIO
from datetime import datetime

# 1. НАЛАШТУВАННЯ (Беремо з Secrets GitHub)
G_TOKEN = os.getenv("G_TOKEN")
EMAIL_PASS = os.getenv("EMAIL_PASS")
EMAIL_USER = "rjktcybr@gmail.com"  # Ваша пошта
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"
FILE_PATH = "solar_ai_base.csv"

def get_askoe_data():
    print("🔎 Пошук звіту АСКОЕ в пошті...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")
        
        # Шукаємо листи від СЕС (можна уточнити тему, якщо треба)
        result, data = mail.search(None, '(UNSEEN)') # Тільки нові або змініть на ALL
        ids = data[0].split()
        
        if not ids:
            print("📭 Нових листів не знайдено.")
            return None

        for latest_id in reversed(ids):
            result, data = mail.fetch(latest_id, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart': continue
                filename = part.get_filename()
                
                if filename and (filename.endswith(".xlsx") or filename.endswith(".xls")):
                    print(f"📥 Знайдено файл: {filename}")
                    data = part.get_payload(decode=True)
                    df = pd.read_excel(BytesIO(data))
                    
                    # ТУТ ЛОГІКА ОБРОБКИ ВАШОГО EXCEL (підлаштуйте назви колонок)
                    # Припустимо, у вас колонки 'Дата/Час' та 'Значення'
                    # df_clean = df[['Час', 'Потужність']] ...
                    
                    # Для тесту просто повертаємо оброблений DF
                    # Переконайтеся, що результат має колонки ['Time', 'Fact_MW']
                    return df 
        return None
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")
        return None

def update_github(new_data):
    print("🚀 Оновлення бази на GitHub...")
    # Тут логіка запису в CSV, яку GitHub Actions виконає сам через 'git push'
    # Тому в самому скрипті достатньо просто зберегти файл локально
    new_data.to_csv(FILE_PATH, index=False)
    print("✅ Файл підготовлено до синхронізації.")

if __name__ == "__main__":
    data = get_askoe_data()
    if data is not None:
        update_github(data)
