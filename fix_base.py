import pandas as pd
import requests
import os
import imaplib
import email
import io
import json
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
NUMERIC_COLS = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb', 'Fact_MW', 'Capacity_MW']

def get_sheet():
    creds_dict = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID).sheet1

def load_df_from_sheet(sheet):
    data = sheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
    if not data:
        return pd.DataFrame(columns=['Time'] + NUMERIC_COLS)
    df = pd.DataFrame(data)
    df['Time'] = pd.to_datetime(df['Time'])
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '.').str.strip(),
                errors='coerce'
            ).fillna(0)
    return df

def fix_value(v, col):
    """Виправляє аномальні значення після проблем з крапкою."""
    if col in ('Forecast_MW', 'Fact_MW') and v > 100:
        return round(v / 1000, 3)
    if col == 'CloudCover' and v > 100:
        return round(v / 10, 1)
    if col == 'Temp' and v > 50:
        return round(v / 10, 1)
    if col == 'WindSpeed' and v > 35:
        return round(v / 10, 1)
    if col == 'PrecipProb' and v > 100:
        return round(v / 10, 1)
    return v

def save_df_to_sheet(sheet, df):
    df = df.sort_values('Time').drop_duplicates('Time').tail(1000).copy()
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).round(3)
    df['Time'] = df['Time'].astype(str)
    rows = []
    for _, row in df.iterrows():
        r = []
        for col in df.columns:
            if col == 'Time':
                r.append(str(row[col]))
            elif col in NUMERIC_COLS:
                r.append(float(row[col]))
            else:
                r.append(row[col])
        rows.append(r)
    sheet.clear()
    sheet.update([df.columns.tolist()] + rows)
    print(f"✅ Google Sheet оновлено. Рядків: {len(df)}")

def main():
    print(f"🚀 СТАРТ ПОВНОГО ПЕРЕЗАПИСУ ФАКТІВ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    sheet = get_sheet()
    df = load_df_from_sheet(sheet)
    print(f"📊 Завантажено з Google Sheet: {len(df)} рядків")

    # Виправляємо всі існуючі числові значення
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: fix_value(v, col))

    # Обнуляємо Fact_MW повністю — перечитаємо з нуля
    df['Fact_MW'] = 0.0
    print("🔄 Fact_MW обнулено — читаємо листи за 45 днів...")

    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")

        # Читаємо листи за 45 днів
        date_from = (datetime.now() - timedelta(days=45)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_from}")')
        ids = data[0].split()

        print(f"📧 Знайдено {len(ids)} листів за 45 днів...")

        for num in reversed(ids):
            _, msg_data = mail.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            for part in msg.walk():
                if part.get_filename() and ('.xls' in part.get_filename().lower()):
                    try:
                        print(f"📄 {part.get_filename()}")
                        raw_data = part.get_payload(decode=True)
                        excel_df = pd.read_excel(io.BytesIO(raw_data), header=None)

                        for i in range(2, len(excel_df)):
                            t_raw = excel_df.iloc[i, 0]
                            t = pd.to_datetime(t_raw, errors='coerce')
                            val_raw = excel_df.iloc[i, 5]
                            val_str = str(val_raw).replace(',', '.').strip()
                            f_val = pd.to_numeric(val_str, errors='coerce')

                            if not pd.isna(t) and not pd.isna(f_val):
                                # Конвертуємо кВт → МВт
                                final_v = round(f_val / 1000, 3) if f_val > 25 else round(f_val, 3)
                                new_facts.append({
                                    'Time': t.replace(minute=0, second=0, microsecond=0),
                                    'Fact_MW': final_v
                                })
                    except Exception as fe:
                        print(f"⚠️ Помилка файлу: {fe}")

        mail.logout()

    except Exception as e:
        print(f"❌ Пошта: {e}")

    if new_facts:
        df_new = pd.DataFrame(new_facts).drop_duplicates('Time')
        # Агрегуємо по годині — беремо максимум (на випадок дублів)
        df_new = df_new.groupby('Time')['Fact_MW'].max().reset_index()

        df = df.set_index('Time')
        df_new = df_new.set_index('Time')
        df.update(df_new)
        df = pd.concat([df, df_new[~df_new.index.isin(df.index)]]).reset_index()
        print(f"✅ Записано фактів: {len(df_new)}")
        print(f"   Діапазон Fact_MW: {df_new['Fact_MW'].min():.3f} .. {df_new['Fact_MW'].max():.3f} МВт")
    else:
        print("📭 Листів з даними не знайдено")

    # Capacity_MW
    df['Capacity_MW'] = 12.5

    # Фінальна перевірка діапазонів
    print(f"\n📊 Фінальні діапазони:")
    for col in ['Forecast_MW', 'Fact_MW', 'Temp', 'WindSpeed', 'CloudCover']:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors='coerce').dropna()
            print(f"   {col}: {vals.min():.2f} .. {vals.max():.2f}")

    save_df_to_sheet(sheet, df)
    print(f"\n🏁 Готово. Рядків: {len(df)}, Остання дата: {df['Time'].max()}")

if __name__ == "__main__":
    main()
