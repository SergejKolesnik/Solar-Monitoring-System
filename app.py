import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="Solar AI Nikopol", layout="wide", initial_sidebar_state="collapsed")

# Стилізація інтерфейсу через CSS
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 2rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
    h1 { color: #ffffff; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-weight: 300; }
    </style>
    """, unsafe_allow_html=True)

def get_weather_data():
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
        # Наша точна модель v2.6 (11.4 MW)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00092 * (1 - df['Clouds']/100 * 0.4)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

# Заголовок
start_d = datetime.now().strftime("%d.%m")
end_d = (datetime.now() + timedelta(days=2)).strftime("%d.%m")

st.markdown(f"<h1>☀️ Solar AI Monitor: Nikopol <span style='font-size:18px; color:gray;'>{start_d} — {end_d}</span></h1>", unsafe_allow_html=True)

df = get_weather_data()

if df is not None:
    # Метрики в стилі Dashboard
    today = df[df['Time'].dt.date == datetime.now().date()]
    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("Сьогодні", f"{today['Power_MW'].sum():.1f} MWh")
    with m2: st.metric("Пік потужності", f"{today['Power_MW'].max():.2f} MW")
    with m3: 
        curr_temp = today.iloc[datetime.now().hour]['Temp']
        st.metric("Температура", f"{curr_temp}°C")
    with m4: st.metric("Станція", "11.4 MW")

    # Створення інтерактивного графіка Plotly
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 1. Хмарність (сірі "гори" на фоні)
    fig.add_trace(go.Scatter(
        x=df['Time'], y=df['Clouds'], 
        name="Хмарність (%)", fill='tozeroy', 
        line=dict(color='rgba(128, 128, 128, 0.2)', width=0),
        fillcolor='rgba(128, 128, 128, 0.1)'
    ))

    # 2. Генерація (Золота лінія з градієнтом)
    fig.add_trace(go.Scatter(
        x=df['Time'], y=df['Power_MW'], 
        name="Генерація (MW)", fill='tozeroy',
        line=dict(color='#f1c40f', width=4),
        fillcolor='rgba(241, 196, 15, 0.15)'
    ))

    # 3. Температура (Червоний пунктир на правій осі)
    fig.add_trace(go.Scatter(
        x=df['Time'], y=df['Temp'], 
        name="Температура (°C)", 
        line=dict(color='#e74c3c', width=2, dash='dot'),
    ), secondary_y=True)

    # Налаштування стилю графіка
    fig.update_layout(
        template="plotly_dark",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=30, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        height=450
    )
    
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(title_text="MW / Clouds %", showgrid=True, gridcolor='rgba(255,255,255,0.05)', secondary_y=False)
    fig.update_yaxes(title_text="°C", secondary_y=True, showgrid=False)

    st.plotly_chart(fig, use_container_width=True)

    # Нижня панель управління
    with st.expander("🛠 Налаштування та детальні дані"):
        st.dataframe(df.style.highlight_max(axis=0, subset=['Power_MW'], color='#3e3e00'))

else:
    st.error("Помилка завантаження даних...")
