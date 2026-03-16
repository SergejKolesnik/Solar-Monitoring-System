import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. НАЛАШТУВАННЯ
st.set_page_config(page_title="SkyGrid: Solar AI v5.4", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. ОТРИМАННЯ ДАНИХ
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
    df_valid = df_history.dropna(subset=['Fact_MW', 'Forecast_MW'])
    if not df_valid.empty:
        df_learn = df_valid[df_valid['Time'] > (now_ua - timedelta(days=7))]
        if not df_learn.empty:
            ai_bias = df_learn['Fact_MW'].sum() / df_learn['Forecast_MW'].sum()
            accuracy = (1 - abs(df_learn['Fact_MW'].sum() - df_learn['Forecast_MW'].sum() * ai_bias) / df_learn['Fact_MW'].sum()) * 100
except: pass

df_forecast['Power_MW'] = df_forecast['Radiation'] * 11.4 * 0.001 * ai_bias

# 4. ІНТЕРФЕЙС
st.markdown("""
    <style>
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
    .nzf-logo { animation: pulse 3s infinite; width: 70px; margin-right: 15px; border-radius: 8px; }
    .title-box { display: flex; align-items: center; margin-bottom: 25px; }
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

    # Експорт в Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_ex = df_plot[['Time', 'Power_MW', 'Clouds', 'Temp']].copy()
        df_ex['Time'] = df_ex['Time'].dt.strftime('%Y-%m-%d %H:%M')
        df_ex.columns = ['Дата/Час', 'План (МВт)', 'Хмарність (%)', 'Темп (°C)']
        df_ex.to_excel(writer,
