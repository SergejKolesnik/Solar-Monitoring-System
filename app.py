import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

from weather_service import fetch_weather_data
from model_engine import train_and_predict
from ui_components import draw_main_chart

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 1. Спроба отримати метеодані
df_f = fetch_weather_data()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

st.title("☀️ SkyGrid Solar AI")

if not df_f.empty:
    try:
        # 2. Завантаження вашої бази з GitHub (вона точно є!)
        url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url)
        
        # 3. ШІ Прогноз
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds.astype(float)
        df_f['Forecast_MW'] = df_f['Forecast_MW'].astype(float) # Сайт
        
        # 4. Нічна логіка
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0
        
        # Відображення метрик
        cols = st.columns(3)
        for i, col in enumerate(cols):
            t_date = (now_ua + timedelta(days=i)).date()
            d_slice = df_f[df_f['Time'].dt.date == t_date]
            if not d_slice.empty:
                col.metric(f"{t_date.strftime('%d.%m')}", f"{d_slice['AI_MW'].sum():.2f} MWh")

        # Малюємо графік (використовуємо ваш успішний код з Полігону)
        draw_main_chart(df_f)
        
    except Exception as e:
        st.error(f"Помилка при обробці бази даних: {e}")
else:
    # Це те, що ми бачимо зараз. Це означає, що fetch_weather_data() повернув пустий список.
    st.error("Критично: Додаток не бачить WEATHER_API_KEY. Будь ласка, перевірте вкладку Secrets у налаштуваннях Streamlit Cloud.")
    st.info("Порада: Скопіюйте ключ з налаштувань 'test-lab' в налаштування цієї програми.")
