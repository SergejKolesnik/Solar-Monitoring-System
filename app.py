import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

from weather_service import fetch_weather_data
from model_engine import train_and_predict
from ui_components import draw_main_chart

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

st.title("☀️ SkyGrid Solar AI")

# Прямий виклик даних
df_f = fetch_weather_data()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

if df_f is not None and not df_f.empty:
    try:
        # Створюємо копію для безпеки
        df_plot = df_f.copy()
        
        # Завантажуємо вашу базу
        url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url)
        
        # Прогноз ШІ
        ai_preds, accuracy = train_and_predict(df_h, df_plot)
        df_plot['AI_MW'] = ai_preds.astype(float)
        
        # Обнулення ночі
        night = (df_plot['Time'].dt.hour < 5) | (df_plot['Time'].dt.hour > 20)
        df_plot.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0
        
        # Метрики
        cols = st.columns(3)
        for i, col in enumerate(cols):
            t_date = (now_ua + timedelta(days=i)).date()
            d_slice = df_plot[df_plot['Time'].dt.date == t_date]
            if not d_slice.empty:
                col.metric(f"{t_date.strftime('%d.%m')}", f"{d_slice['AI_MW'].sum():.2f} MWh")

        # Графік (використовуємо надійні назви Forecast_MW та AI_MW)
        draw_main_chart(df_plot)
        
    except Exception as e:
        st.error(f"Помилка обробки: {e}")
else:
    st.error("Дані від метеосервісу все ще не надходять.")
    # ТЕХНІЧНА ДІАГНОСТИКА ДЛЯ НАС
    st.write("🔧 Технічна діагностика:")
    st.write(f"Наявність ключа в системі: {'WEATHER_API_KEY' in st.secrets}")
    if st.button("Примусово очистити кеш"):
        st.cache_data.clear()
        st.rerun()
