import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v7.0", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def get_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation&include=hours,days&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15); res.raise_for_status()
        data = res.json()
        h_list = []
        for d in data['days']:
            for hr in d['hours']:
                h_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Radiation': hr.get('solarradiation', 0),
                    'Clouds': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0)
                })
        return pd.DataFrame(h_list)
    except Exception as e: return str(e)

# 2. РОЗУМНА АНАЛІТИКА ТА КОРЕКЦІЯ
df_forecast = get_weather_data()
if isinstance(df_forecast, str): st.error(f"Error: {df_forecast}"); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias, accuracy, df_history = 1.0, 0, None
daily_stats = pd.DataFrame()

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_history = pd.read_csv(repo_url)
    df_history['Time'] = pd.to_datetime(df_history['Time'])
    
    # --- КОРЕКЦІЯ НА СЬОГОДНІ (Intraday Bias) ---
    # Беремо сьогоднішні дані з бази, де вже є Факт
    df_today_fact = df_history[(df_history['Time'].dt.date == now_ua.date()) & (df_history['Fact_MW'].notna())]
    
    if not df_today_fact.empty and df_today_fact['Forecast_MW'].sum() > 0:
        # Розраховуємо коефіцієнт саме по сьогоднішньому ранку
        ai_bias = df_today_fact['Fact_MW'].sum() / df_today_fact['Forecast_MW'].sum()
    else:
        # Якщо за сьогодні ще немає факту, беремо середній за 3 дні
        df_prev = df_history.dropna(subset=['Fact_MW', 'Forecast_MW']).tail(72)
        if not df_prev.empty:
            ai_bias = df_prev['Fact_MW'].sum() / df_prev['Forecast_MW'].sum()

    # --- СТАТИСТИКА ПО ДНЯХ ДЛЯ ГРАФІКА ---
    df_history['Date'] = df_history['Time'].dt.date
    daily_stats = df_history.groupby('Date').agg({
        'Fact_MW': 'sum',
        'Forecast_MW': 'sum'
    }).reset_index().tail(10) # Останні 10 днів
    
    # Розрахунок точності для метрики
    if not df_history.dropna(subset=['Fact_MW', 'Forecast_MW']).empty:
        last_day = daily_stats.iloc[-2] # Позавчорашній повний день
        if last_day['Fact_MW'] > 0:
            accuracy = (1 - abs(last_day['Fact_MW'] - last_day['Forecast_MW'])/last_day['Fact_MW']) * 100

except: pass

# Застосування корекції до прогнозу
df_forecast['Power_MW'] = df_forecast['Radiation'] * 11.4 * 0.001 * ai_bias

# 3. ІНТЕРФЕЙС
st.markdown("""
    <style>
    .metric-card { background: rgba(255,255,255,0.05); padding:15px; border-radius:15px; text-align:center; border:1px solid rgba(255,255,255,0.1); }
    .nzf-logo { width: 60px; margin-right: 15px; border-radius: 8px; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""<div style="display:flex; align-items:center; margin-bottom:20px;">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" class="nzf-logo">
    <h1>SkyGrid Solar AI <span style="color:#00ff7f; font-size:20px;">v7.0</span></h1>
</div>""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
s_today = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['Power_MW'].sum()
c1.metric("ПЛАН НА СЬОГОДНІ", f"{s_today:.1f} MWh")
c2.metric("КОЕФІЦІЄНТ AI", f"{ai_bias:.2f}x")
c3.metric("ТОЧНІСТЬ СИСТЕМИ", f"{accuracy:.1f}%")
c4.metric("ОНОВЛЕНО", now_ua.strftime("%H:%M"))

tab1, tab2 = st.tabs(["📈 АНАЛІЗ ТА ПРОГНОЗ", "🌦 ДЕТАЛЬНА ПОГОДА"])

with tab1:
    # ГРАФІК 1: ПОРІВНЯННЯ ПО ДНЯХ (ПЛАН VS ФАКТ)
    st.subheader("📊 Порівняння генерації по днях (MWh)")
    if not daily_stats.empty:
        fig_daily = go.Figure()
        fig_daily.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW'], name="Прогноз (План)", marker_color='#444'))
        fig_daily.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Fact_MW'], name="Реал (Факт АСКОЕ)", marker_color='#00ff7f'))
        fig_daily.update_layout(barmode='group', height=300, template="plotly_dark", margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig_daily, use_container_width=True)
    
    st.markdown("---")
    
    # ГРАФІК 2: ОПЕРАТИВНИЙ ПЛАН НА 72 ГОДИНИ
    st.subheader("⏱ Оперативний графік на 3 доби (з корекцією AI)")
    df_p = df_forecast[df_forecast['Time'] >= pd.Timestamp(
