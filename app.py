import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v7.2", layout="wide")
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

# 2. АНАЛІТИКА ТА КОРЕКЦІЯ
df_forecast = get_weather_data()
if isinstance(df_forecast, str): st.error(f"Error: {df_forecast}"); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias, accuracy = 1.0, 0
daily_stats = pd.DataFrame()

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_history = pd.read_csv(repo_url)
    df_history['Time'] = pd.to_datetime(df_history['Time'])
    
    # Виправляємо BIAS: порівнюємо факти з планами, які БУЛИ в базі
    df_valid = df_history.dropna(subset=['Fact_MW', 'Forecast_MW'])
    if not df_valid.empty:
        df_recent = df_valid[df_valid['Time'] > (now_ua - timedelta(days=5))]
        if not df_recent.empty:
            ai_bias = df_recent['Fact_MW'].sum() / df_recent['Forecast_MW'].sum()

    # --- ПІДГОТОВКА СТАТИСТИКИ ПО ДНЯХ ---
    df_history['Date'] = df_history['Time'].dt.date
    # Беремо тільки останні 7 днів від сьогоднішньої дати
    min_date = (now_ua - timedelta(days=7)).date()
    df_filtered = df_history[df_history['Date'] >= min_date]
    
    daily_stats = df_filtered.groupby('Date').agg({
        'Fact_MW': 'sum',
        'Forecast_MW': 'sum'
    }).reset_index()
    
    # Розрахунок точності по останньому повному дню (вчора)
    yesterday_date = (now_ua - timedelta(days=1)).date()
    y_data = daily_stats[daily_stats['Date'] == yesterday_date]
    if not y_data.empty and y_data['Fact_MW'].iloc[0] > 0:
        f, p = y_data['Fact_MW'].iloc[0], y_data['Forecast_MW'].iloc[0]
        accuracy = (1 - abs(f - p)/f) * 100
except: pass

# Корекція майбутнього прогнозу
df_forecast['Power_MW'] = df_forecast['Radiation'] * 11.4 * 0.001 * ai_bias

# 3. ІНТЕРФЕЙС
st.markdown("""
    <style>
    .nzf-logo { width: 60px; margin-right: 15px; border-radius: 8px; }
    .main-title { display: flex; align-items: center; margin-bottom: 30px; }
    [data-testid="stMetricValue"] { font-size: 28px !important; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""<div class="main-title">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" class="nzf-logo">
    <h1 style='margin:0;'>SkyGrid Solar AI <span style='color:#00ff7f; font-size:18px;'>v7.2</span></h1>
</div>""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
s_today = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['Power_MW'].sum()
c1.metric("ПЛАН НА СЬОГОДНІ", f"{s_today:.1f} MWh")
c2.metric("КОЕФІЦІЄНТ AI", f"{ai_bias:.2f}x")
c3.metric("ТОЧНІСТЬ ВЧОРА", f"{accuracy:.1f}%")
c4.metric("СТАТУС", "Синхронно", delta="Online")

tab1, tab2 = st.tabs(["📊 АНАЛІТИКА ТА ПРОГНОЗ", "🌦 МЕТЕОУМОВИ"])

with tab1:
    st.subheader("📅 Порівняльний аналіз генерації (MWh)")
    
    if not daily_stats.empty:
        fig_daily = go.Figure()
        # План (Сірий)
        fig_daily.add_trace(go.Bar(
            x=daily_stats['Date'], y=daily_stats['Forecast_MW'],
            name="План", marker_color='#444',
            text=daily_stats['Forecast_MW'].round(1), textposition='outside'
        ))
        # Факт (Зелений)
        fig_daily.add_trace(go.Bar(
            x=daily_stats['Date'], y=daily_stats['Fact_MW'],
            name="Факт АСКОЕ", marker_color='#00ff7f',
            text=daily_stats['Fact_MW'].round(1), textposition='outside'
        ))
        
        fig_daily.update_layout(
            barmode='group', height=350, template="plotly_dark",
            margin=dict(l=0,r=0,t=30,b=0),
            xaxis=dict(type='category'), # Щоб дні не розтягувалися
            yaxis_title="MWh"
        )
        st.plotly_chart(fig_daily, use_container_width=True)
        
        # Маленька таблиця підсумків для точності
        with st.expander("📝 Відкрити таблицю значень за тиждень"):
            df_table = daily_stats.copy()
            df_table['Відхилення (MWh)'] = (df_table['Fact_MW'] - df_table['Forecast_MW']).round(2)
            df_table.columns = ['Дата', 'Факт (MWh)', 'План (MWh)', 'Різниця']
            st.dataframe(df_table.sort_values('Дата', ascending=False), use_container_width=True)

    st.markdown("---")
    st.subheader("⏱ Оперативний графік на 72 години (Корегований)")
    
    df_p = df_forecast[df_forecast['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    fig_hours = go.Figure()
    fig_hours.add_trace(go.Scatter(
        x=df_p['Time'], y=df_p['Power_MW'], 
        fill='tozeroy', name="МВт План", 
        line=dict(color='#00ff7f', width=3)
    ))
    fig_hours.update_layout(height=300, template="plotly_dark", margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig_hours, use_container_width=True)

    # Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_ex = df_p[['Time', 'Power_MW']].copy()
        df_ex.columns = ['Дата/Час', 'План МВт (корегований)']
        df_ex.to_excel(writer, index=False)
    st.download_button("📥 Завантажити Excel План", output.getvalue(), f"Plan_AI_{now_ua.strftime('%d%m')}.xlsx")

with tab2:
    # Дизайн метеоумов (v4.6)
    df_t = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]
    if not df_t.empty:
        cur = df_t[df_t['Time'].dt.hour == now_ua.hour].iloc[0] if now_ua.hour in df_t['Time'].dt.hour.values else df_t.iloc[0]
        st.markdown(f"<h3 style='text-align:center;'>Нікополь: {now_ua.strftime('%d.%m.%Y')}</h3>", unsafe_allow_html=True)
        cl1, cl2 = st.columns([1.2, 2])
        with cl1:
            st.markdown(f"""<div style='background:rgba(255,255,255,0.05); padding:25px; border-radius:15px; border:1px solid rgba(255,255,255,0.1); text-align:center;'>
                <p style='font-size:60px; margin:0;'>☀️</p>
                <p style='font-size:35px; font-weight:bold; margin:0;'>{cur['Temp']:.1f}°C</p>
                <p style='color:gray;'>Хмарність: {cur['Clouds']:.0f}%</p>
            </div>""", unsafe_allow_html=True)
        with cl2:
            st.area_chart(df_t.set_index('Time')[['Radiation']], color="#FFD700", height=220)
