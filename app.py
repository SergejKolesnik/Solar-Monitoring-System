import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v8.9", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# Ініціалізація локального сховища в сесії, щоб сторінка не була порожньою
if 'last_valid_data' not in st.session_state:
    st.session_state.last_valid_data = None
if 'last_fetch_time' not in st.session_state:
    st.session_state.last_fetch_time = None

def get_weather_data():
    api_key = st.secrets["WEATHER_API_KEY"]
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.56,34.39/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation&include=hours,days&key={api_key}&contentType=json"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Radiation': hr.get('solarradiation', 0),
                        'Clouds': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0)
                    })
            df = pd.DataFrame(h_list)
            # Оновлюємо кеш при успіху
            st.session_state.last_valid_data = df
            st.session_state.last_fetch_time = datetime.now(UA_TZ).strftime("%H:%M:%S")
            return df, "OK"
        else:
            return None, f"Помилка API {response.status_code}"
    except Exception as e:
        return None, f"Збій мережі: {str(e)}"

# 2. ЛОГІКА ЗАВАНТАЖЕННЯ (БЕЗ ПАДІННЯ)
df_forecast, status_msg = get_weather_data()

# Якщо зараз помилка, але є старі дані - використовуємо їх
using_cache = False
if df_forecast is None:
    if st.session_state.last_valid_data is not None:
        df_forecast = st.session_state.last_valid_data
        using_cache = True
    else:
        st.error(f"❌ Немає зв'язку та немає кешованих даних: {status_msg}")
        st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 3. БАЗА ТА AI
ai_bias = 1.0
try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_history = pd.read_csv(repo_url)
    df_history['Time'] = pd.to_datetime(df_history['Time'])
    df_v = df_history.dropna(subset=['Fact_MW', 'Forecast_MW'])
    if not df_v.empty:
        df_recent = df_v[df_v['Time'] > (now_ua - timedelta(days=3))]
        if not df_recent.empty:
            ai_bias = df_recent['Fact_MW'].sum() / df_recent['Forecast_MW'].sum()
    
    df_history['Date'] = df_history['Time'].dt.date
    daily_stats = df_history.groupby('Date').agg({'Fact_MW': 'sum', 'Forecast_MW': 'sum'}).reset_index()
    daily_stats = daily_stats[daily_stats['Date'] <= now_ua.date()].tail(7)
except: daily_stats = pd.DataFrame()

# Керування потужністю
st.sidebar.header("⚙️ Керування SkyGrid")
manual_boost = st.sidebar.slider("Ручна корекція (%)", 50, 300, 100) / 100
final_bias = ai_bias * manual_boost

df_forecast['Raw_MW'] = df_forecast['Radiation'] * 11.4 * 0.001
df_forecast['AI_MW'] = df_forecast['Raw_MW'] * final_bias

# 4. ІНТЕРФЕЙС
st.markdown(f"""
    <div style="display:flex; align-items:center; margin-bottom:10px;">
        <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:55px; border-radius:8px; margin-right:15px;">
        <h1 style='margin:0;'>SkyGrid Solar AI v8.9</h1>
    </div>
""", unsafe_allow_html=True)

# ПОВІДОМЛЕННЯ ПРО СТАТУС ДАНИХ
if using_cache:
    st.warning(f"⚠️ Метеосайт недоступний ({status_msg}). Показую прогноз, збережений о {st.session_state.last_fetch_time}")
else:
    st.success(f"✅ Дані оновлено о {st.session_state.last_fetch_time}")

c1, c2, c3 = st.columns(3)
s_ai = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
s_raw = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['Raw_MW'].sum()

c1.metric("ОЦІНКА SKYGRID (AI)", f"{s_ai:.1f} MWh", delta=f"{final_bias:.2f}x")
c2.metric("ПРОГНОЗ ПО САЙТУ", f"{s_raw:.1f} MWh")
c3.metric("АВТО-КОЕФІЦІЄНТ", f"{ai_bias:.2f}x")

tab1, tab2 = st.tabs(["📊 АНАЛІТИКА", "🌦 МЕТЕОУМОВИ"])

with tab1:
    st.subheader("📅 Порівняння виробітки (7 днів)")
    if not daily_stats.empty:
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW'], name="Сайт", marker_color='#666'))
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW']*final_bias, name="SkyGrid AI", marker_color='#1f77b4'))
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f', text=daily_stats['Fact_MW'].round(1), textposition='outside'))
        fig_d.update_layout(barmode='group', height=350, template="plotly_dark", margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("---")
    st.subheader("⏱ Оперативний прогноз (72 години)")
    df_p = df_forecast[df_forecast['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    fig_h = go.Figure()
    fig_h.add_trace(go.Scatter(x=df_p['Time'], y=df_p['AI_MW'], fill='tozeroy', name="AI План", line=dict(color='#00ff7f', width=3)))
    fig_h.add_trace(go.Scatter(x=df_p['Time'], y=df_p['Raw_MW'], name="Сайт", line=dict(color='gray', width=1, dash='dot')))
    
    # Розрахунок сум на графіку
    sums = df_p.groupby(df_p['Time'].dt.date)['AI_MW'].sum()
    for date, val in sums.items():
        fig_h.add_annotation(x=f"{date} 12:00:00", y=df_p[df_p['Time'].dt.date == date]['AI_MW'].max()+0.5,
                             text=f"Σ {val:.1f} MWh", showarrow=False, font=dict(color="#FFD700"))
    
    fig_h.update_layout(height=380, template="plotly_dark")
    st.plotly_chart(fig_h, use_container_width=True)

with tab2:
    df_t = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]
    if not df_t.empty:
        cur = df_t[df_t['Time'].dt.hour == now_ua.hour].iloc[0] if now_ua.hour in df_t['Time'].dt.hour.values else df_t.iloc[0]
        st.markdown(f"<h4 style='text-align:center;'>Нікополь: {now_ua.strftime('%d.%m.%Y')}</h4>", unsafe_allow_html=True)
        col1, col2 = st.columns([1, 2])
        with col1:
            st.markdown(f"""<div style='background:rgba(255,255,255,0.05); padding:25px; border-radius:15px; border:1px solid rgba(255,255,255,0.1); text-align:center;'>
                <p style='font-size:60px; margin:0;'>☀️</p>
                <p style='font-size:35px; font-weight:bold; margin:0;'>{cur['Temp']:.1f}°C</p>
                <p style='color:gray;'>Хмарність: {cur['Clouds']:.0f}%</p>
            </div>""", unsafe_allow_html=True)
        with col2:
            st.area_chart(df_t.set_index('Time')[['Radiation']], color="#FFD700", height=220)
