import pandas as pd
import json
import os
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
NUMERIC_COLS = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb', 'Fact_MW', 'Capacity_MW']

def get_sheet():
    creds_dict = json.loads(os.getenv('GOOGLE_CREDENTIALS'))
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID).sheet1

def fix_numeric(val, col):
    """Конвертує значення в float, виправляє кВт→МВт де потрібно."""
    try:
        v = float(str(val).replace(',', '.').strip())
    except:
        return 0.0

    # Forecast_MW і Fact_MW: реальний максимум ~15 МВт
    # Якщо значення > 100 — це кВт без крапки, ділимо на 1000
    if col in ('Forecast_MW', 'Fact_MW') and v > 100:
        return round(v / 1000, 3)

    # CloudCover: максимум 100%
    # Якщо > 100 — теж проблема з крапкою (наприклад 998 → 99.8)
    if col == 'CloudCover' and v > 100:
        return round(v / 10, 1)

    # WindSpeed: максимум ~50 м/с
    if col == 'WindSpeed' and v > 50:
        return round(v / 10, 1)

    # PrecipProb: максимум 100%
    if col == 'PrecipProb' and v > 100:
        return round(v / 10, 1)

    return round(v, 3)

def main():
    print("🚀 Старт виправлення бази...")
    sheet = get_sheet()

    data = sheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
    if not data:
        print("❌ Таблиця порожня")
        return

    df = pd.DataFrame(data)
    print(f"📊 Завантажено {len(df)} рядків")

    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time'])

    # Виправляємо всі числові колонки
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: fix_numeric(v, col))

    # Capacity_MW — заповнюємо 12.5 скрізь
    df['Capacity_MW'] = 12.5

    df = df.sort_values('Time').drop_duplicates('Time')
    df['Time'] = df['Time'].astype(str)

    # Формуємо рядки для запису
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
    print(f"✅ Готово! Виправлено {len(df)} рядків.")

if __name__ == "__main__":
    main()
