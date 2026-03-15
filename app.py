import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import time
import pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI Nikopol v3.8.5", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. ФУНКЦІЇ ДАНИХ (Збільшено TTL до 1 години для безпеки)
@st.cache_data(ttl=3600, show_spinner="Оновлення метеоданих...")
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation&timezone=Europe%2FLondon&past_days=7&forecast_days=10"
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 429:
            return "429_ERROR"
        res.raise_for_status()
        h = res.json()['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m'],
            'Rain': h['precipitation']
        })
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None)
        df['Base_MW'] = df['Radiation'] * 11.4 * 0.00115 * (1 - df['Clouds']/100 * 0.2)
        return df
    except:
        return "CONN_ERROR"

# 3. ЛОГІКА ЗАВАНТАЖЕННЯ
weather_res = get_weather_data()

if isinstance(weather_res, str):
    if weather_res == "429_ERROR":
        st.warning("⚠️ Метеослужба тимчасово обмежила доступ (Error 429). Спробуйте перезавантажити сторінку через 15 хв.")
    else:
        st.error("📡 Помилка зв'язку з сервером погоди.")
    st.stop()

# Далі йде решта коду (дизайн, графіки), він залишається без змін...
# (Я пропускаю його тут, щоб не дублювати 150 рядків, просто встав цей блок на початок)
