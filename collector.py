import imaplib
import email
import pandas as pd
import os
import re
from github import Github
from datetime import datetime
import io

# --- НАЛАШТУВАННЯ (Вставити своє) ---
EMAIL_USER = "твоя_пошта@gmail.com"
EMAIL_PASS = "твій_пароль_додатка" 
IMAP_SERVER = "imap.gmail.com"

GITHUB_TOKEN = "твій_токен_github"
REPO_NAME = "SergejKolesnik/Solar-Monitoring-System"
CSV_FILE_PATH = "solar_ai_base.csv"

def get_data_from_emails():
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        # Шукаємо листи за темою "Звіт про роботу установ"
        result, data = mail.search(None, '(SUBJECT "Звіт про роботу установ")')
        ids = data[0].split()
        
        all_new_rows = []

        # Перевіряємо останні 10 листів, щоб закрити пропуски за кілька днів
        for e_id in ids[-10:]:
            res, msg_data = mail.fetch(e_id, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    for part in msg.walk():
                        filename = part.get_filename()
                        # ФІЛЬТР: шукаємо файл reportCEC (новий формат)
                        if filename and "reportCEC" in filename:
                            print(f"✅ Обробка файлу: {filename}")
                            content = part.get_payload(decode=True)
                            
                            # Читаємо Excel з пам'яті
                            df_temp = pd.read_excel(io.BytesIO(content))
                            
                            # Очищення та вибір потрібних колонок (Time та Fact_MW)
                            # Припускаємо, що структура: 1-ша колонка - час, 2-га - МВт
                            df_temp = df_temp.iloc[:, [0, 1]] 
                            df_temp.columns = ['Time', 'Fact_MW']
                            all_new_rows.append(df_temp)
        
        mail.logout()
        if all_new_rows:
            return pd.concat(all_new_rows).drop_duplicates(subset=['Time'])
        return None
    except Exception as e:
        print(f"❌ Помилка пошти: {e}")
        return None

def update_github_csv(new_df):
    try:
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(REPO_NAME)
        contents = repo.get_contents(CSV_FILE_PATH)
        
        # Завантажуємо існуючий CSV
        old_df = pd.read_csv(io.StringIO(contents.decoded_content.decode('utf-8')))
        
        # Об'єднуємо, видаляємо дублікати та сортуємо по часу
        final_df = pd.concat([old_df, new_df]).drop_duplicates(subset=['Time'], keep='last')
        final_df['Time'] = pd.to_datetime(final_df['Time'])
        final_df = final_df.sort_values('Time')
        
        # Оновлюємо файл на GitHub
        csv_buffer = io.StringIO()
        final_df.to_csv(csv_buffer, index=False)
        repo.update_file(contents.path, f"Update AI base: {datetime.now().strftime('%Y-%m-%d %H:%M')}", csv_buffer.getvalue(), contents.sha)
        print("🚀 Базу на GitHub успішно оновлено!")
    except Exception as e:
        print(f"❌ Помилка GitHub: {e}")

# ЗАПУСК
if __name__ == "__main__":
    new_data = get_data_from_emails()
    if new_data is not None:
        update_github_csv(new_data)
    else:
        print("📭 Нових даних у пошті не знайдено.")
