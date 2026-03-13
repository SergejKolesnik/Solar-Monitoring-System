import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import time

# Налаштування сторінки
st.set_page_config(page_title="Solar AI Monitor Nikopol", layout="wide", initial_sidebar_state="collapsed")

# Стилізація інтерфейсу (Dark Theme)
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    h1 { color: #ffffff; font-family: 'Segoe UI', sans-serif; font-weight: 300; padding-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=600)
def get_weather_data():
    """Отримання прогнозу погоди на 3 дні для Нікополя"""
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m&timezone=auto&forecast_days=3"
    try:
        data = requests.get(url).json()
        h = data['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m']
        })
        # Модель v2.6 (11.4 MW)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00092 * (1 - df['Clouds']/100 * 0.4)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except:
        return None

# Заголовок з динамічними датами
start_d = datetime.now().strftime("%d.%m")
end_d = (datetime.now() + timedelta(days=2)).strftime("%d.%m")
st.markdown(f"<h1>☀️ Solar AI Monitor: Nikopol <span style='font-size:18px; color:gray;'>{start_d} — {end_d}</span></h1>", unsafe_allow_html=True)

df_forecast = get_weather_data()

if df_forecast is not None:
    # --- БЛОК ДАНИХ АСКОЕ (ФАКТ) ---
    df_fact = None
    try:
        # Додаємо мітку часу, щоб обійти кешування GitHub
        repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time())}"
        df_fact = pd.read_csv(repo_url)
        df_fact['Time'] = pd.to_datetime(df_fact['Time'])
    except:
        pass

    # Метрики Dashboard
    today_date = datetime.now().date()
    today_forecast = df_forecast[df_forecast['Time'].dt.date == today_date]
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Прогноз на сьогодні", f"{today_forecast['Power_MW'].sum():.1f} MWh")
    with m2:
        if df_fact is not None:
            # Рахуємо суму факту саме за сьогодні
            today_fact = df_fact[df_fact['Time'].dt.date == today_date]
            fact_val = today_fact['Fact_MW'].sum()
            # Якщо сьогодні ще мало даних, покажемо суму за останні 24 години з файлу
            if fact_val == 0: fact_val = df_fact['Fact_MW'].sum()
            st.metric("Факт АСКОЕ", f"{fact_val:.1f} MWh")
        else:
            st.metric("Факт АСКОЕ", "Оновлення...")
    with m3:
        curr_hour = datetime.now().hour
        curr_temp = today_forecast.iloc[curr_hour]['Temp'] if curr_hour < len(today_forecast) else 0
        st.metric("Температура зараз", f"{curr_temp}°C")
    with m4:
        st.metric("Потужність СЕС", "11.4 MW")

    # --- СТВОРЕННЯ ГРАФІКА Plotly ---
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 1. Хмарність (сірий фон)
    fig.add_trace(go.Scatter(
        x=df_forecast['Time'], y=df_forecast['Clouds'], 
        name="Хмарність (%)", fill='tozeroy', 
        line=dict(color='rgba(128, 128, 128, 0.2)', width=0),
        fillcolor='rgba(128, 128, 128, 0.1)',
        hoverinfo='skip'
    ))

    # 2. Прогноз генерації (Золота лінія)
    fig.add_trace(go.Scatter(
        x=df_forecast['Time'], y=df_forecast['Power_MW'], 
        name="Прогноз (MW)", fill='tozeroy',
        line=dict(color='#f1c40f', width=4),
        fillcolor='rgba(241, 196, 15, 0.15)'
    ))

    # 3. Факт АСКОЕ (Червона лінія)
    if df_fact is not None:
        fig.add_trace(go.Scatter(
            x=df_fact['Time'], y=df_fact['Fact_MW'], 
            name="Факт АСКОЕ (MW)", 
            line=dict(color='#e74c3c', width=3),
            mode='lines+markers',
            marker=dict(
