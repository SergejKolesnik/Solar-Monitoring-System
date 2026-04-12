import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

from weather_service import fetch_weather_data
from model_engine import train_and_predict
from ui_components import draw_main_chart, draw_training_stats

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 1. Дані
raw_df = fetch_weather_data()
df_f = raw_df.copy() 
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
    df_h = pd.read_csv(url)
    
    if not df_f.empty:
        # Готуємо дані для графіка
        df_f['Прогноз сайту (МВт)'] = df_f['Forecast_MW'].astype(float)
        
        # ШІ
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['Прогноз ШІ (МВт)'] = ai_preds.astype(float)
        
        # Ніч = 0
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['Прогноз ШІ (МВт)', 'Прогноз сайту (МВт)']] = 0.0
    else: accuracy = 0
except:
    df_h, accuracy = pd.DataFrame(), 0

# --- ІНТЕРФЕЙС ---
st.title("☀️ SkyGrid Solar AI")
if not df_f.empty:
    draw_main_chart(df_f)
    
    # Кнопка Excel
    output = io.BytesIO()
    ex_df = df_f.head(72)[['Time', 'Прогноз сайту (МВт)', 'Прогноз ШІ (МВт)']].copy()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        ex_df.to_excel(writer, index=False)
    st.download_button("📥 Excel План", output.getvalue(), "Solar_Plan.xlsx")
else:
    st.error("Помилка: дані не завантажені. Перевірте Secrets.")
