import pandas as pd
import os
from datetime import datetime, timedelta

CSV_FILE = "solar_ai_base.csv"

def sync_data(forecast_df, askoe_data=None):
    """
    forecast_df: дані з Visual Crossing (Time, Forecast_MW)
    askoe_data: дані з пошти (Time, Fact_MW)
    """
    
    # 1. Завантажуємо існуючу базу або створюємо нову
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW'])

    # 2. ОНОВЛЮЄМО ПРОГНОЗ (на 3 дні вперед)
    # Ми додаємо нові прогнози, якщо їх ще немає в базі
    forecast_df['Time'] = pd.to_datetime(forecast_df['Time'])
    for _, row in forecast_df.iterrows():
        if row['Time'] not in df_base['Time'].values:
            # Створюємо новий рядок з порожнім фактом
            new_row = pd.DataFrame({'Time': [row['Time']], 'Forecast_MW': [row['Forecast_MW']], 'Fact_MW': [None]})
            df_base = pd.concat([df_base, new_row], ignore_index=True)
        else:
            # Оновлюємо існуючий прогноз (якщо він змінився)
            df_base.loc[df_base['Time'] == row['Time'], 'Forecast_MW'] = row['Forecast_MW']

    # 3. ОНОВЛЮЄМО ФАКТ (з пошти)
    if askoe_data is not None:
        askoe_data['Time'] = pd.to_datetime(askoe_data['Time'])
        for _, row in askoe_data.iterrows():
            if row['Time'] in df_base['Time'].values:
                # Вписуємо факт у вже існуючий рядок, де був прогноз
                df_base.loc[df_base['Time'] == row['Time'], 'Fact_MW'] = row['Fact_MW']
            else:
                # Якщо прогнозу раптом не було (збій), просто додаємо факт
                new_row = pd.DataFrame({'Time': [row['Time']], 'Fact_MW': [row['Fact_MW']], 'Forecast_MW': [None]})
                df_base = pd.concat([df_base, new_row], ignore_index=True)

    # Сортуємо по часу та зберігаємо
    df_base = df_base.sort_values('Time').drop_duplicates('Time', keep='last')
    df_base.to_csv(CSV_FILE, index=False)
    print("Базу синхронізовано успішно.")

# ПРИКЛАД ВИКОРИСТАННЯ:
# df_weather = get_weather_forecast_3days() # Твій запит до API
# df_mail = parse_askoe_email() # Твій парсер пошти
# sync_data(df_weather, df_mail)
