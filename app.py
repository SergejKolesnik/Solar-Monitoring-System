import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

from weather_service import fetch_weather_data
from model_engine import train_and_predict
from ui_components import draw_main_chart, draw_training_stats

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 1. Завантаження даних
df_f = fetch_weather_data()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
    df_h = pd.read_csv(url)
    
    if not df_f.empty:
        # ШІ робить прогноз
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        
        # Перейменовуємо для графіків та таблиці
        df_f['Прогноз ШІ (МВт)'] = ai_preds
        df_f['Прогноз сайту (МВт)'] = df_f['Forecast_MW']
        
        # Обнуляємо ніч
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['Прогноз ШІ (МВт)', 'Прогноз сайту (МВт)']] = 0.0
    else:
        accuracy = 0
except:
    df_h, accuracy = pd.DataFrame(), 0

# --- ІНТЕРФЕЙС ---
st.title("☀️ SkyGrid Solar AI")
tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with tabs[0]:
    # Метрики
    if not df_f.empty:
        c1, c2, c3 = st.columns(3)
        for i, col in enumerate([c1, c2, c3]):
            t_date = (now_ua + timedelta(days=i)).date()
            d_data = df_f[df_f['Time'].dt.date == t_date]
            if not d_data.empty:
                ai_s = d_data['Прогноз ШІ (МВт)'].sum()
                si_s = d_data['Прогноз сайту (МВт)'].sum()
                col.metric(f"{t_date.strftime('%d.%m')}", f"{ai_s:.2f} МВт·год", f"{ai_s-si_s:+.2f}")

        # Графік
        draw_main_chart(df_f)

        # Кнопка Excel (тільки 2 колонки + Час)
        st.write("---")
        output = io.BytesIO()
        # Готуємо просту таблицю для людей
        excel_df = df_f.head(72)[['Time', 'Прогноз сайту (МВт)', 'Прогноз ШІ (МВт)']].copy()
        excel_df.columns = ['Дата та час', 'Прогноз сайту (МВт)', 'Прогноз ШІ (МВт)']
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            excel_df.to_excel(writer, index=False, sheet_name='План генерації')
        
        st.download_button(
            label="📥 Завантажити ПЛАН ГЕНЕРАЦІЇ (Excel)",
            data=output.getvalue(),
            file_name=f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

with tabs[1]:
    draw_training_stats(df_h, accuracy)

with tabs[2]:
    st.dataframe(df_h.tail(50), use_container_width=True)
