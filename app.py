import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time

# 1. Налаштування сторінки
st.set_page_config(page_title="Solar AI Nikopol", layout="wide", initial_sidebar_state="collapsed")

# 2. Стилізація (Темна тема та картки ШІ)
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .ai-card { 
        background: rgba(241, 196, 15, 0.05); 
        border: 1px solid #f1c40f; 
        border-radius: 10px; 
        padding: 20px;
        margin-top: 20px;
    }
    h2 { color: #ffffff; font-weight: 300; border-left: 5px solid #f1c40f; padding-left: 15px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=600)
def get_weather_data():
    """Отримання погоди: 1 день минулого + 3 дні прогнозу"""
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m&timezone=auto&past_days=1&forecast_days=3"
    try:
        data = requests.get(url).json()
        h = data['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m']
        })
        # Математична модель v2.6 (11.4 MW)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00092 * (1 - df['Clouds']/100 * 0.4)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except Exception as e:
        st.error(f"Помилка метеоданих: {e}")
        return None

# --- ЗАВАНТАЖЕННЯ ДАНИХ ---
df_forecast = get_weather_data()
df_fact = None
try:
    # Обхід кешу GitHub через позначку часу
    v_tag = int(time.time())
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
except:
