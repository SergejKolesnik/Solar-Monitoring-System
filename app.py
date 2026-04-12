import streamlit as st
import pandas as pd
import time, pytz
from datetime import datetime, timedelta

# Імпортуємо всі наші сервіси
from weather_service import fetch_weather_data
from model_engine import train_and_predict
from ui_components import draw_main_chart, draw_training_stats

st.set_page_config(page_title="SkyGrid Solar AI v22.0", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 1. Отримуємо погоду
df_f = fetch_weather_data()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 2. Отримуємо базу АСКОЕ та запускаємо ШІ
try:
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time']).dt.floor('h')
    
    if not df_f.empty:
        # ШІ робить свою роботу
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds
        # Обнуляємо ніч
        df_f.loc[(df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20), 'AI_MW'] = 0
    else:
        accuracy = 0
except:
    df_h, accuracy = pd.DataFrame(), 0

# 3. МАЛЮЄМО ІНТЕРФЕЙС
st.title("☀️ SkyGrid Solar AI (Modular Edition)")
tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with tabs[0]:
    if not df_f.empty:
        draw_main_chart(df_f)
    else:
        st.warning("Чекаємо на дані від метеосервісу...")

with tabs[1]:
    draw_training_stats(df_h, accuracy)

with tabs[2]:
    st.dataframe(df_h.tail(50), use_container_width=True)
