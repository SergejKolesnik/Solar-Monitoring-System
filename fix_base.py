import pandas as pd
import os
import json
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


def main():
    from datetime import datetime
    print(f"🚀 СТАРТ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    sheet = get_sheet()
    data = sheet.get_all_records(value_render_option='UNFORMATTED_VALUE')
    df = pd.DataFrame(data)
    print(f"📊 Завантажено: {len(df)} рядків")

    df['Time'] = pd.to_datetime(df['Time'])
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '.').str.strip(),
                errors='coerce'
            ).fillna(0)

    # Виправляємо аномалії БЕЗ обнулення Fact_MW
    fixes = [
        ('Forecast_MW', 15,  1000),
        ('Fact_MW',     15,  1000),
        ('CloudCover',  100, 10),
        ('Temp',        50,  10),
        ('WindSpeed',   35,  10),
        ('PrecipProb',  100, 10),
    ]
    for col, threshold, divisor in fixes:
        if col in df.columns:
            mask = df[col] > threshold
            df.loc[mask, col] = (df.loc[mask, col] / divisor).round(3)
            print(f"🔧 {col}: виправлено {mask.sum()} рядків")

    df['Capacity_MW'] = 12.5

    print(f"\n📊 Діапазони після виправлення:")
    for col in ['Forecast_MW', 'Fact_MW', 'Temp', 'WindSpeed', 'CloudCover']:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors='coerce').dropna()
            nz = vals[vals > 0]
            print(f"   {col}: 0..{vals.max():.3f} (ненульових: {len(nz)})")

    # Зберігаємо
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
    print(f"\n✅ Готово. Рядків: {len(df)}, Остання дата: {df['Time'].max()}")


if __name__ == "__main__":
    main()
