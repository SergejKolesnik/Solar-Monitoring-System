import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz

# 1. НАЛАШТУВАННЯ
st.set_page_config(page_title="SkyGrid: Solar AI v5.1", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. ОТРИМАННЯ ДАНИХ (Тільки прогноз на майбутнє)
@st.cache_data(ttl=3600)
def get_weather_forecast():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,precip&include=hours,days&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15); res.raise_for_status()
        data = res.json()
        hours_list = []
        for day in data['days']:
            for hr in day['hours']:
                hours_list.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Radiation': hr.get('solarradiation', 0),
                    'Clouds': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'Rain': hr.get('precip', 0)
                })
        return pd.DataFrame(hours_list)
    except Exception as e: return f"Error: {e}"

def get_weather_icon(clouds, rain):
    if rain > 0.2: return "🌧️"
    if clouds > 70: return "☁️"
    if clouds > 30: return "⛅"
    return "☀️"

# 3. ПІДГОТОВКА ДАНИХ
df_forecast = get_weather_forecast()
if isinstance(df_forecast, str): st.error(df_forecast); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
df_today = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]
current_data = df_today[df_today['Time'].dt.hour == now_ua.hour].iloc[0] if not df_today.empty else df_forecast.iloc[0]

# --- ЛОГІКА НАВЧАННЯ ШІ ---
ai_bias, accuracy, df_history = 1.0, 0, None
try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_history = pd.read_csv(repo_url)
    df_history['Time'] = pd.to_datetime(df_history['Time'])
    
    # Фільтруємо рядки, де є і Факт, і Прогноз
    df_valid = df_history.dropna(subset=['Fact_MW', 'Forecast_MW'])
    if not df_valid.empty:
        # Беремо дані за останні 7 днів для навчання
        df_learn = df_valid[df_valid['Time'] > (now_ua - timedelta(days=7))]
        if not df_learn.empty:
            ai_bias = df_learn['Fact_MW'].sum() / df_learn['Forecast_MW'].sum()
            # Рахуємо точність як відхилення
            error = abs(df_learn['Fact_MW'].sum() - df_learn['Forecast_MW'].sum() * ai_bias) / df_learn['Fact_MW'].sum()
            accuracy = (1 - error) * 100
except: pass

# Розрахунок потужності на майбутнє з урахуванням вивченого BIAS
df_forecast['Power_MW'] = df_forecast['Radiation'] * 11.4 * 0.001 * ai_bias

# 4. ІНТЕРФЕЙС
st.markdown("""
    <style>
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
    .nzf-logo { animation: pulse 3s infinite; width: 70px; margin-right: 15px; border-radius: 8px; }
    .title-box { display: flex; align-items: center; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""
    <div class="title-box">
        <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" class="nzf-logo">
        <h1 style='margin:0;'>SkyGrid: Solar AI Nikopol</h1>
    </div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📊 МОНІТОРИНГ ТА НАВЧАННЯ", "🌦 ПРОГНОЗ ПОГОДИ"])

with tab1:
    st.markdown("### 📅 План генерації (MWh)")
    m1, m2, m3, m4 = st.columns(4)
    
    s1 = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['Power_MW'].sum()
    s2 = df_forecast[df_forecast['Time'].dt.date == (now_ua + timedelta(days=1)).date()]['Power_MW'].sum()
    s3 = df_forecast[df_forecast['Time'].dt.date == (now_ua + timedelta(days=2)).date()]['Power_MW'].sum()

    m1.metric("СЬОГОДНІ", f"{s1:.1f}")
    m2.metric("ЗАВТРА", f"{s2:.1f}")
    m3.metric("ПІСЛЯЗАВТРА", f"{s3:.1f}")
    m4.metric("ТОЧНІСТЬ ШІ", f"{accuracy:.1f} %", f"{ai_bias:.2f}x bias")

    st.markdown("---")
    st.subheader("📈 Оперативний графік (72 години)")
    df_plot = df_forecast[df_forecast['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_plot['Time'], y=df_plot['Power_MW'], fill='tozeroy', name="План МВт", line=dict(color='#00ff7f', width=3)))
    fig.update_layout(height=300, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    if df_history is not None:
        st.subheader("🧠 Ретроспектива: Як ШІ вивчив об'єкт")
        # Порівнюємо реальний Факт з тим Прогнозом, який був у базі
        df_hist_plot = df_history.dropna(subset=['Fact_MW']).tail(168) # Остання неділя
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=df_hist_plot['Time'], y=df_hist_plot['Fact_MW'], name="ФАКТ (АСКОЕ)", line=dict(color='#ff4b4b', width=3)))
        if 'Forecast_MW' in df_hist_plot.columns:
            fig_h.add_trace(go.Scatter(x=df_hist_plot['Time'], y=df_hist_plot['Forecast_MW']*ai_bias, name="ПЛАН ШІ", line=dict(color='white', width=2, dash='dot')))
        fig_h.update_layout(height=300, template="plotly_dark")
        st.plotly_chart(fig_h, use_container_width=True)

with tab2:
    # Твоя незмінна друга сторінка
    f_date = df_today['Time'].dt.date.iloc[0].strftime("%d.%m.%Y")
    st.markdown(f"<h1 style='text-align: center;'>📅 Прогноз на сьогодні: <span style='color:#FFD700;'>{f_date}</span></h1>", unsafe_allow_html=True)
    c1, c2 = st.columns([1.2, 2])
    with c1:
        st.markdown(f"""
            <div style='background:rgba(255,255,255,0.05); padding:25px; border-radius:20px; border:1px solid rgba(255,255,255,0.1); text-align:center;'>
                <p style='font-size:80px; margin:0;'>{get_weather_icon(current_data['Clouds'], current_data['Rain'])}</p>
                <div style='display:flex; justify-content:space-around;'>
                    <div><p style='color:gray; font-size:14px; margin:0;'>ТЕМП</p><p style='font-size:32px; font-weight:bold; margin:0;'>{current_data['Temp']:.0f}°</p></div>
                    <div><p style='color:gray; font-size:14px; margin:0;'>ХМАР</p><p style='font-size:32px; font-weight:bold; margin:0;'>{current_data['Clouds']:.0f}%</p></div>
                </div>
                <hr style='opacity:0.1; margin:20px 0;'>
                <div style='display:flex; justify-content:space-around;'>
                    <div><p style='color:gray; font-size:14px; margin:0;'>РАДІАЦІЯ</p><p style='font-size:24px; font-weight:bold; color:#FFD700; margin:0;'>{current_data['Radiation']:.0f}W</p></div>
                    <div><p style='color:gray; font-size:14px; margin:0;'>ОПАДИ</p><p style='font-size:24px; font-weight:bold; color:#3498db; margin:0;'>{current_data['Rain']:.1f}мм</p></div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            st.area_chart(df_today.set_index('Time')[['Radiation']], color="#FFD700", height=270)
