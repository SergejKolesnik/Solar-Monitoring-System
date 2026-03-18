import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v7.5", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def get_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation&include=hours,days&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15).json()
        h_list = []
        for d in res['days']:
            for hr in d['hours']:
                h_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Radiation': hr.get('solarradiation', 0),
                    'Clouds': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0)
                })
        return pd.DataFrame(h_list)
    except Exception as e: return str(e)

def get_icon(clouds):
    return "☀️" if clouds < 30 else "⛅" if clouds < 70 else "☁️"

# 2. АНАЛІТИКА ШІ ТА ФІЛЬТРАЦІЯ БАЗИ
df_forecast = get_weather_data()
if isinstance(df_forecast, str): st.error(f"Error: {df_forecast}"); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias, accuracy = 1.0, 0.0
daily_stats = pd.DataFrame()

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_history = pd.read_csv(repo_url)
    df_history['Time'] = pd.to_datetime(df_history['Time'])
    
    # ПРИБИРАЄМО ПОМИЛКОВІ ДАТИ (тільки поточний місяць/рік)
    df_history = df_history[df_history['Time'].dt.year == now_ua.year]
    df_history = df_history[df_history['Time'].dt.month == now_ua.month]

    # РОЗРАХУНОК КОЕФІЦІЄНТА (BIAS)
    df_valid = df_history.dropna(subset=['Fact_MW', 'Forecast_MW'])
    df_valid = df_valid[df_valid['Forecast_MW'] > 0.1] # Тільки світлий час
    
    if not df_valid.empty:
        df_recent = df_valid[df_valid['Time'] > (now_ua - timedelta(days=5))]
        if not df_recent.empty:
            ai_bias = df_recent['Fact_MW'].sum() / df_recent['Forecast_MW'].sum()

    # ПІДГОТОВКА ПОРІВНЯННЯ ПО ДНЯХ
    df_history['Date'] = df_history['Time'].dt.date
    daily_stats = df_history.groupby('Date').agg({'Fact_MW': 'sum', 'Forecast_MW': 'sum'}).reset_index()
    daily_stats = daily_stats.tail(7) # Тільки останній тиждень

    # Точність по вчорашньому дню
    yest = (now_ua - timedelta(days=1)).date()
    y_row = daily_stats[daily_stats['Date'] == yest]
    if not y_row.empty and y_row['Fact_MW'].iloc[0] > 0:
        accuracy = (1 - abs(y_row['Fact_MW'].iloc[0] - y_row['Forecast_MW'].iloc[0]*ai_bias)/y_row['Fact_MW'].iloc[0]) * 100
except: pass

# ЖОРСТКЕ КОРЕГУВАННЯ ПРОГНОЗУ
df_forecast['Power_MW'] = df_forecast['Radiation'] * 11.4 * 0.001 * ai_bias

# 3. ІНТЕРФЕЙС
st.markdown("""
    <style>
    .nzf-logo { width: 55px; border-radius: 8px; margin-right: 15px; }
    .main-header { display: flex; align-items: center; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""<div class="main-header">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" class="nzf-logo">
    <h1 style='margin:0;'>SkyGrid Solar AI <span style='color:#00ff7f; font-size:16px;'>v7.5</span></h1>
</div>""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
s_today = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['Power_MW'].sum()
c1.metric("ПЛАН НА СЬОГОДНІ", f"{s_today:.1f} MWh")
c2.metric("КОЕФІЦІЄНТ AI", f"{ai_bias:.2f}x")
c3.metric("ТОЧНІСТЬ ВЧОРА", f"{max(0, accuracy):.1f}%")
c4.metric("СТАТУС", "Синхронно")

tab1, tab2 = st.tabs(["📊 АНАЛІТИКА ТА ПРОГНОЗ", "🌦 МЕТЕОУМОВИ"])

with tab1:
    st.subheader("📅 Порівняльний аналіз (MWh)")
    if not daily_stats.empty:
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW'], name="План", marker_color='#444', text=daily_stats['Forecast_MW'].round(1), textposition='outside'))
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f', text=daily_stats['Fact_MW'].round(1), textposition='outside'))
        fig_d.update_layout(barmode='group', height=300, template="plotly_dark", margin=dict(l=0,r=0,t=30,b=0), xaxis=dict(type='category'))
        st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("---")
    st.subheader("⏱ Оперативний графік на 72 години")
    
    df_p = df_forecast[df_forecast['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    
    # РОЗРАХУНОК СУМ ДЛЯ ПІДПИСІВ НА ГРАФІКУ
    daily_sums = df_p.groupby(df_p['Time'].dt.date)['Power_MW'].sum()
    
    fig_h = go.Figure()
    fig_h.add_trace(go.Scatter(x=df_p['Time'], y=df_p['Power_MW'], fill='tozeroy', name="МВт", line=dict(color='#00ff7f', width=3)))
    
    # Додаємо анотації (цифри MWh) над кожним днем
    for date, total in daily_sums.items():
        fig_h.add_annotation(
            x=f"{date} 12:00:00", y=df_p[df_p['Time'].dt.date == date]['Power_MW'].max() + 0.5,
            text=f"<b>{total:.1f} MWh</b>", showarrow=False, font=dict(color="#FFD700", size=14),
            bgcolor="rgba(0,0,0,0.5)", bordercolor="#FFD700", borderpad=4
        )
        
    fig_h.update_layout(height=350, template="plotly_dark", margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig_h, use_container_width=True)

    with st.expander("📝 Відкрити таблицю значень"):
        st.dataframe(daily_stats.sort_values('Date', ascending=False), use_container_width=True)

with tab2:
    # --- ПОВЕРНЕННЯ СУВОРОЇ ДРУГОЇ СТОРІНКИ ---
    df_t = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]
    if not df_t.empty:
        cur = df_t[df_t['Time'].dt.hour == now_ua.hour].iloc[0] if now_ua.hour in df_t['Time'].dt.hour.values else df_t.iloc[0]
        st.markdown(f"<h3 style='text-align:center;'>Нікополь: {now_ua.strftime('%d.%m.%Y')}</h3>", unsafe_allow_html=True)
        
        # Використовуємо контейнери для фіксації блоків
        c_left, c_right = st.columns([1.2, 2])
        with c_left:
            st.markdown(f"""<div style='background:rgba(255,255,255,0.05); padding:30px; border-radius:15px; border:1px solid rgba(255,255,255,0.1); text-align:center;'>
                <p style='font-size:70px; margin:0;'>{get_icon(cur['Clouds'])}</p>
                <p style='font-size:40px; font-weight:bold; margin:0;'>{cur['Temp']:.1f}°C</p>
                <p style='color:gray;'>Хмарність: {cur['Clouds']:.0f}%</p>
            </div>""", unsafe_allow_html=True)
        with c_right:
            with st.container(border=True):
                st.area_chart(df_t.set_index('Time')[['Radiation']], color="#FFD700", height=230)
        
        st.markdown("<br>", unsafe_allow_html=True)
        # Погодинні картки знизу
        t_cols = st.columns(7)
        d_hrs = df_t[df_t['Time'].dt.hour.isin([8, 10, 12, 14, 16, 18, 20])]
        for i, (idx, row) in enumerate(d_hrs.iterrows()):
            with t_cols[i]:
                st.markdown(f"""<div style='background:rgba(255,255,255,0.03); padding:10px; border-radius:10px; border:1px solid rgba(255,255,255,0.07); text-align:center;'>
                    <p style='font-size:12px; color:gray; margin:0;'>{row['Time'].strftime('%H:%M')}</p>
                    <p style='font-size:24px; margin:5px 0;'>{get_icon(row['Clouds'])}</p>
                    <p style='font-size:16px; font-weight:bold; margin:0;'>{row['Temp']:.0f}°</p>
                </div>""", unsafe_allow_html=True)
