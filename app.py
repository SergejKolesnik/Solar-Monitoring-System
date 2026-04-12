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
        # ПЕРШИМ ДІЛОМ створюємо колонку сайту (копіюємо з Forecast_MW)
        df_f['Прогноз сайту (МВт)'] = df_f['Forecast_MW']
        
        # ШІ робить прогноз
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['Прогноз ШІ (МВт)'] = ai_preds
        
        # Обнуляємо ніч (з 21:00 до 05:00)
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['Прогноз ШІ (МВт)', 'Прогноз сайту (МВт)']] = 0.0
    else:
        accuracy = 0
except Exception as e:
    st.error(f"Помилка: {e}")
    df_h, accuracy = pd.DataFrame(), 0

# --- ІНТЕРФЕЙС ---
st.title("☀️ SkyGrid Solar AI")
tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with tabs[0]:
    if not df_f.empty:
        c1, c2, c3 = st.columns(3)
        for i, col in enumerate([c1, c2, c3]):
            t_date = (now_ua + timedelta(days=i)).date()
            d_data = df_f[df_f['Time'].dt.date == t_date]
            if not d_data.empty:
                ai_s = d_data['Прогноз ШІ (МВт)'].sum()
                si_s = d_data['Прогноз сайту (МВт)'].sum()
                col.metric(f"{t_date.strftime('%d.%m')}", f"{ai_s:.2f} МВт·год", f"{ai_s-si_s:+.2f}")

        # Малюємо графік
        draw_main_chart(df_f)

        # Кнопка Excel (тільки 3 колонки українською)
        st.write("---")
        output = io.BytesIO()
        excel_df = df_f.head(72)[['Time', 'Прогноз сайту (МВт)', 'Прогноз ШІ (МВт)']].copy()
        excel_df.columns = ['Дата та час', 'Прогноз сайту (МВт)', 'Прогноз ШІ (МВт)']
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            excel_df.to_excel(writer, index=False, sheet_name='План')
        
        st.download_button(
            label="📥 Завантажити ПЛАН (Excel)",
            data=output.getvalue(),
            file_name=f"Plan_{now_ua.strftime('%d_%m')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
