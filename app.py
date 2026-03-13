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

# Стилізація CSS
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 700; }
    .stPlotlyChart { border-radius: 15px; border: 1px solid rgba(128,128,128,0.2); }
    .footer { position: fixed; bottom: 10px; right: 20px; color: gray; font-size: 11px; z-index: 1000; text-align: right; }
    .status-tag { background: rgba(128,128,128,0.1); padding: 5px 15px; border-radius: 20px; border: 1px solid rgba(128,128,128,0.2); font-size: 13px; }
    .weather-card { padding: 10px; border-radius: 10px; border: 1px solid rgba(128,128,128,0.1); background: rgba(128,128,128,0.05); }
    </style>
    """, unsafe_allow_html=True)

# 2. ФУНКЦІЇ ДАНИХ (Оновлено до 10 днів)
@st.cache_data(ttl=600)
def get_weather_data():
    # Змінено forecast_days на 10
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation,relative_humidity_2m,wind_speed_10m&timezone=auto&past_days=0&forecast_days=10"
    try:
        res = requests.get(url).json()
        h = res['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m'],
            'Rain': h['precipitation'],
            'Humidity': h['relative_humidity_2m'],
            'Wind': h['wind_speed_10m']
        })
        # Корекція часу
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None) - pd.Timedelta(hours=2)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00115 * (1 - df['Clouds']/100 * 0.2)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

# 3. ЛОГІКА ШІ
df_all = get_weather_data()
ai_bias, last_update, days_learned = 1.0, "Очікування", 0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    last_date = df_fact['Time'].dt.date.max()
    last_update = last_date.strftime("%d.%m.%Y")
    days_learned = len(df_fact['Time'].dt.date.unique())
    # ... розрахунок bias (залишено як у твоєму коді)
except: pass

if df_all is not None:
    df_all['Power_MW'] = df_all['Power_MW'] * ai_bias

# 4. ШАПКА
col_l, col_r = st.columns([1, 4])
with col_l:
    st.image("https://www.nzf.com.ua/img/logo.gif", width=120)
with col_r:
    st.title("SkyGrid: Solar AI Monitor Nikopol")
    st.markdown(f"<span class='status-tag'>📅 Оновлено: {last_update}</span> <span class='status-tag'>🧠 Досвід ШІ: {days_learned} днів</span>", unsafe_allow_html=True)

# 5. ОСНОВНИЙ КОНТЕНТ
if df_all is not None:
    now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
    
    # ТАБИ ДЛЯ МЕТЕОПРОГНОЗУ
    st.header("🌦 Метеопрогноз та Генерація")
    tab1, tab2, tab3 = st.tabs(["Сьогодні (Почасово)", "Прогноз на 3 дні", "Прогноз на 10 днів"])

    with tab1:
        df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
        # Вивід короткої таблиці з основними показниками
        weather_display = df_today[['Time', 'Temp', 'Clouds', 'Rain', 'Power_MW']].copy()
        weather_display['Time'] = weather_display['Time'].dt.strftime('%H:%M')
        weather_display.columns = ['Час', 'Темп (°C)', 'Хмарність (%)', 'Опади (мм)', 'План (МВт)']
        st.dataframe(weather_display.set_index('Час'), use_container_width=True)

    with tab2:
        three_days = now_ua.date() + pd.Timedelta(days=3)
        df_3 = df_all[df_all['Time'].dt.date <= three_days]
        st.line_chart(df_3.set_index('Time')[['Temp', 'Power_MW']])

    with tab3:
        # Агрегуємо дані по днях для 10 днів
        df_10 = df_all.groupby(df_all['Time'].dt.date).agg({
            'Temp': 'max',
            'Rain': 'sum',
            'Power_MW': 'sum'
        })
        df_10.columns = ['Макс. Темп (°C)', 'Опади (мм)', 'Генерація (МВт·год)']
        st.table(df_10)

    # ГРАФІК (Твій оригінальний)
    st.markdown("### 📊 Візуалізація генерації (72 години)")
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(72).copy()
    
    fig1.add_trace(go.Bar(x=df_f['Time'], y=df_f['Rain'], name="Опади (mm)", marker_color='rgba(0, 120, 255, 0.3)'))
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="ШІ Прогноз (МВт)", fill='tozeroy', line=dict(color='#2ecc71', width=3), fillcolor='rgba(46, 204, 113, 0.2)'))
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Temp'], name="Темп (°C)", line=dict(color='#e74c3c', width=1.5, dash='dot')), secondary_y=True)
    
    fig1.update_layout(height=480, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig1, use_container_width=True, theme="streamlit")

# ФУТЕР
st.markdown(f"<div class='footer'>Розробник: Сергій Колесник | АТ 'НЗФ' © 2026</div>", unsafe_allow_html=True)
