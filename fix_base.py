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

def fix_anomalies(df):
    mask = df['Forecast_MW'] > 15
    df.loc[mask, 'Forecast_MW'] = (df.loc[mask, 'Forecast_MW'] / 1000).round(3)
    print(f"🔧 Forecast_MW виправлено: {mask.sum()} рядків")

    mask = df['Fact_MW'] > 15
    df.loc[mask, 'Fact_MW'] = (df.loc[mask, 'Fact_MW'] / 1000).round(3)
    print(f"🔧 Fact_MW виправлено: {mask.sum()} рядків")

    mask = df['CloudCover'] > 100
    df.loc[mask, 'CloudCover'] = (df.loc[mask, 'CloudCover'] / 10).round(1)
    print(f"🔧 CloudCover виправлено: {mask.sum()} рядків")

    mask = df['Temp'] > 50
    df.loc[mask, 'Temp'] = (df.loc[mask, 'Temp'] / 10).round(1)
    print(f"🔧 Temp виправлено: {mask.sum()} рядків")

    mask = df['WindSpeed'] > 35
    df.loc[mask, 'WindSpeed'] = (df.loc[mask, 'WindSpeed'] / 10).round(1)
    print(f"🔧 WindSpeed виправлено: {mask.sum()} рядків")

    mask = df['PrecipProb'] > 100
    df.loc[mask, 'PrecipProb'] = (df.loc[mask, 'PrecipProb'] / 10).round(1)
    print(f"🔧 PrecipProb виправлено: {mask.sum()} рядків")

    return df

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
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    sheet = get_sheet()
    df = load_df_from_sheet(sheet)
    print(f"📊 Завантажено: {len(df)} рядків")

    df = fix_anomalies(df)

    df['Fact_MW'] = 0.0
    print("🔄 Fact_MW обнулено — читаємо листи за 45 днів...")

    new_facts = []
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(os.getenv('EMAIL_USER'), os.getenv('EMAIL_PASS'))
        mail.select("INBOX")

        date_from = (datetime.now() - timedelta(days=45)).strftime("%d-%b-%Y")
        _, data = mail.search(None, f'(SINCE "{date_from}")')
        ids = data[0].split()
        print(f"📧 Знайдено {len(ids)} листів за 45 днів...")

        for num in reversed(ids):
            try:
                _, msg_data = mail.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])

                for part in msg.walk():
                    if part.get_filename() and ('.xls' in part.get_filename().lower()):
                        try:
                            print(f"📄 {part.get_filename()}")
                            raw_data = part.get_payload(decode=True)
                            if raw_data is None:
                                continue
                            excel_df = pd.read_excel(io.BytesIO(raw_data), header=None)

                            for i in range(2, len(excel_df)):
                                try:
                                    t_raw = excel_df.iloc[i, 0]
                                    if t_raw is None or str(t_raw).strip() == '':
                                        continue
                                    t = pd.to_datetime(t_raw, errors='coerce')
                                    if t is None or pd.isna(t):
                                        continue

                                    val_raw = excel_df.iloc[i, 5]
                                    if val_raw is None:
                                        continue
                                    val_str = str(val_raw).replace(',', '.').strip()
                                    f_val = pd.to_numeric(val_str, errors='coerce')
                                    if pd.isna(f_val):
                                        continue

                                    final_v = round(f_val / 1000, 3) if f_val > 25 else round(f_val, 3)
                                    new_facts.append({
                                        'Time': t.replace(minute=0, second=0, microsecond=0),
                                        'Fact_MW': final_v
                                    })
                                except Exception:
                                    continue

                        except Exception as fe:
                            print(f"⚠️ Файл: {fe}")
            except Exception as me:
                print(f"⚠️ Лист: {me}")

        mail.logout()

    except Exception as e:
        print(f"❌ Пошта: {e}")

    if new_facts:
        df_new = pd.DataFrame(new_facts)
        df_new = df_new.groupby('Time')['Fact_MW'].max().reset_index()
        df = df.set_index('Time')
        df_new = df_new.set_index('Time')
        df.update(df_new)
        df = pd.concat([df, df_new[~df_new.index.isin(df.index)]]).reset_index()
        print(f"✅ Записано фактів: {len(df_new)}")
        print(f"   Fact_MW діапазон: {df_new['Fact_MW'].min():.3f} .. {df_new['Fact_MW'].max():.3f} МВт")
    else:
        print("📭 Листів з даними не знайдено")

    df['Capacity_MW'] = 12.5

    print(f"\n📊 Фінальні діапазони:")
    for col in ['Forecast_MW', 'Fact_MW', 'Temp', 'WindSpeed', 'CloudCover']:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors='coerce').dropna()
            non_zero = vals[vals > 0]
            print(f"   {col}: 0 .. {vals.max():.3f} (ненульових: {len(non_zero)})")

    save_df_to_sheet(sheet, df)
    print(f"\n🏁 Готово. Рядків: {len(df)}, Остання дата: {df['Time'].max()}")

if __name__ == "__main__":
    main()
