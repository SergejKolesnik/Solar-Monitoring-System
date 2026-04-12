import streamlit as st
import pandas as pd
import time, pytz
import io
from datetime import datetime, timedelta

# Імпортуємо наші сервіси
from weather_service import fetch_weather_data
from model_engine import train_and_predict
from ui_components import draw_main_chart, draw_training_stats

st.set_page_config(page_title="SkyGrid Solar AI v22.1", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 1. Отримуємо дані
df_f = fetch_weather_data()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time']).dt.floor('h')
    
    if not df_f.empty:
        # ШІ робить свою роботу
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds
        
        # Обнуляємо ніч для обох колонок
        night_mask = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night_mask, 'AI_MW'] = 0
        df_f.loc[night_mask, 'Forecast_MW'] = 0
    else:
        accuracy = 0
except:
    df_h, accuracy = pd.DataFrame(), 0

# --- ГРАФІЧНА ЧАСТИНА ---
st.title("☀️ SkyGrid Solar AI")
st.caption(f"АТ «НЗФ» • Оновлено: {now_ua.strftime('%H:%M:%S')}")

tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with tabs[0]:
    # 2. ВЕЛИКІ ПОКАЗНИКИ НА 3 ДНІ
    c1, c2, c3 = st.columns(3)
    cols = [c1, c2, c3]
    
    for i in range(3):
        target_date = (now_ua + timedelta(days=i)).date()
        day_data = df_f[df_f['Time'].dt.date == target_date]
        
        if not day_data.empty:
            ai_sum = day_data['AI_MW'].sum()
            site_sum = day_data['Forecast_MW'].sum()
            diff = ai_sum - site_sum
            
            cols[i].metric(
                label=f"📅 {target_date.strftime('%d.%m')}",
                value=f"{ai_sum:.2f} MWh",
                delta=f"{diff:+.2f} від сайту",
                delta_color="normal"
            )
            cols[i].caption(f"Прогноз сайту: {site_sum:.2f} MWh")

    # 3. ГРАФІК
    draw_main_chart(df_f)

    # 4. КНОПКА ЗАВАНТАЖЕННЯ EXCEL
    if not df_f.empty:
        st.write("---")
        # Готуємо файл у пам'яті
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Беремо перші 72 години для експорту
            export_df = df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW', 'CloudCover', 'Temp']].copy()
            export_df.columns = ['Час', 'Прогноз сайту (MW)', 'План АІ (MW)', 'Хмарність (%)', 'Темп (C)']
            export_df.to_excel(writer, index=False, sheet_name='Forecast')
        
        st.download_button(
            label="📥 Завантажити погодинний план (Excel)",
            data=output.getvalue(),
            file_name=f"SkyGrid_Forecast_{now_ua.strftime('%d_%m')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

with tabs[1]:
    draw_training_stats(df_h, accuracy)

with tabs[2]:
    st.dataframe(df_h.tail(50), use_container_width=True)
