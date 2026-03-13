import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime
import time
import pytz
from io import BytesIO

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI Nikopol", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# Стилізація CSS (збережено твій стиль + додано футер)
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 700; }
    .stPlotlyChart { border-radius: 15px; border: 1px solid rgba(128,128,128,0.2); }
    .ai-card { background: rgba(0, 255, 127, 0.05); border: 1px solid #00ff7f; border-radius: 10px; padding: 15px; }
    .footer { position: fixed; bottom: 10px; right: 20px; color: gray; font-size: 11px; z-index: 1000; text-align: right; }
    .status-tag { background: rgba(128,128,128,0.1); padding: 5px 15px; border-radius: 20px; border: 1px solid rgba(128,128,128,0.2); font-size: 13px; }
    .progress-bg { background: rgba(128,128,128,0.2); border-radius: 10px; height: 8px; width: 150px; display: inline-block; margin-left: 10px; vertical-align: middle; }
    .progress-fill { background: #00ff7f; height: 100%; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# 2. ФУНКЦІЇ ДАНИХ
@st.cache_data(ttl=600)
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation&timezone=auto&past_days=7&forecast_days=3"
    try:
        res = requests.get(url).json()
        h = res['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m'],
            'Rain': h['precipitation']
        })
        # Корекція часу
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None) - pd.Timedelta(hours=2)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00115 * (1 - df['Clouds']/100 * 0.2)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

# 3. ЛОГІКА ШІ ТА ФАКТУ
df_all = get_weather_data()
df_fact = None
ai_bias, last_update, days_learned = 1.0, "Немає даних",
