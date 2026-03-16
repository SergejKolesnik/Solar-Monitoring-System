import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import time
import pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v3.9", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. СТИЛІ (Залишаємо твій фірмовий дизайн)
st.markdown("""
    <style>
    .block-container { padding: 2.5rem 1rem 0rem 1rem; }
    .status-tag { background: rgba(128,128,128,0.1); padding: 4px 12px; border-radius: 15px; border: 1px solid rgba(128,128,128,0.2); font-size: 13px; }
    .weather-card-industrial { flex: 1; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(0, 212, 255, 0.2); border-radius: 8px; padding: 8px 2px; text-align: center; min-width: 0; }
    .day-card-hybrid { background: #1e2124; border: 1px solid #32383e; border-radius: 12px; padding: 12px 5px; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

# 3. НОВА ФУНКЦІЯ ПОГОДИ (Visual Crossing)
@st.cache_data(ttl=3600)
def get_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        # Запитуємо прогноз на 7 днів + минулі 2 дні для аналізу
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,precip&include=hours&key={api_key}&contentType=json"
        
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        hours_list = []
        for day in data['days']:
            for hr in day['hours']:
                full_time = f"{day['datetime']} {hr['datetime']}"
                hours_list.append({
                    'Time': pd.to_datetime(full_time),
                    'Radiation': hr.get('solarradiation', 0),
                    'Clouds': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'Rain': hr.get('precip', 0)
                })
        
        df = pd.DataFrame(hours_list)
        # Коригування формули під дані Visual Crossing (вони дають W/m2 середнє за годину)
        df['Base_MW'] = df['Radiation'] * 11.4 * 0.0011 * (1 - df['Clouds']/100 * 0.18)
        return df
    except Exception as e:
        return f"ERROR: {str(e)}"

def get_weather_icon(clouds, rain):
    if rain > 0.2: return "🌧️"
    if clouds > 70: return "☁️"
    if clouds > 30: return "⛅"
    return "☀️"

# 4. ЗАВАНТАЖЕННЯ
weather_res = get_weather_data()
if isinstance(weather_res, str):
    st.error(f"📡 Помилка метеосервера: {weather_res}")
    if "WEATHER_API_KEY" not in st.secrets:
        st.info("Будь ласка, додайте WEATHER_API_KEY в Secrets вашого додатка.")
    st.stop()

df_all = weather_res
df_fact = None
ai_bias, last_update, days_learned = 1.0, "...", 0

# Завантаження бази з GitHub
try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    last_update = df_fact['Time'].dt.date.max().strftime("%d.%m.%Y")
    days_learned = len(df_fact['Time'].dt.date.unique())
    
    # Розрахунок корекції ШІ
    last_full_day = df_fact['Time'].dt.date.max()
    f_sum = df_fact[df_fact['Time'].dt.date == last_full_day]['Fact_MW'].sum()
    p_sum = df_all[df_all['Time'].dt.date == last_full_day]['Base_MW'].sum()
    if p_sum > 0: ai_bias = f_sum / p_sum
except: pass

df_all['Power_MW'] = df_all['Base_MW'] * ai_bias
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
df_today = df_all[df_all['Time'].dt.date == now_ua.date()]

# 5. ІНТЕРФЕЙС
col_logo, col_title = st.columns([0.6, 5])
with col_logo: st.image("https://www.nzf.com.ua/img/logo.gif", width=100)
with col_title:
    st.markdown(f"""
        <div style='display:flex; justify-content:space-between; align-items:center;'>
            <h2 style='margin:0;'>SkyGrid: Solar AI Nikopol <span style='color:#00d4ff;font-size:14px;'>v3.9 (VC)</span></h2>
            <div style='display:flex; gap:15px; align-items:center;'>
                <span class='status-tag'>📅 АСКОЕ: <b>{last_update}</b></span>
                <span class='status-tag'>🧠 ШІ: <b>{days_learned} дн.</b></span>
            </div>
        </div>
    """, unsafe_allow_html=True)

tab1, tab2 = st.tabs(["🚀 МОНІТОРИНГ", "🌦 ПРОГНОЗ ПОГОДИ"])

with tab1:
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("ШІ ПЛАН (СЬОГОДНІ)", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:.2f}x bias")
    with m2: 
        t_now = df_today[df_today['Time'].dt.hour == now_ua.hour]['Temp'].values[0] if not df_today.empty else 0
        st.metric("ТЕМПЕРАТУРА", f"{t_now}°C")
    with m3: st.metric("СТАТУС СЕС", "11.4 MW Online")

    fig1 = go.Figure()
    # Показуємо прогноз на найближчі 48 годин
    df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(48)
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="План ШІ (МВт)", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    fig1.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
    st.plotly_chart(fig1, use_container_width=True)

    if df_fact is not None:
        st.subheader("📊 Порівняння Факт vs План (Останні дні)")
        df_hist_fact = df_fact.tail(72)
        fig_learn = go.Figure()
        fig_learn.add_trace(go.Scatter(x=df_hist_fact['Time'], y=df_hist_fact['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#ff4b4b', width=3)))
        fig_learn.update_layout(height=250, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color='white'))
        st.plotly_chart(fig_learn, use_container_width=True)

with tab2:
    if df_today is not None and not df_today.empty:
        # 1. ГОЛОВНИЙ ВІДЖЕТ (Поточний стан)
        now_hour = datetime.now(UA_TZ).hour
        current_data = df_today[df_today['Time'].dt.hour == now_hour].iloc[0] if now_hour < len(df_today) else df_today.iloc[0]
        
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown(f"""
                <div style='background: linear-gradient(135deg, #2c3e50, #000000); padding: 30px; border-radius: 20px; border: 1px solid #34495e;'>
                    <div style='color: #00d4ff; font-size: 14px; text-transform: uppercase;'>Зараз у Нікополі</div>
                    <div style='font-size: 64px; font-weight: 800; margin: 10px 0;'>{current_data['Temp']:.0f}°C</div>
                    <div style='font-size: 20px;'>{get_weather_icon(current_data['Clouds'], current_data['Rain'])} Прогноз сонячності</div>
                </div>
            """, unsafe_allow_html=True)
            
        with c2:
            # 2. ПРОСТИЙ ГРАФІК РАДІАЦІЇ (Бронебійний)
            st.markdown("<p style='color:gray; font-size:12px; margin-bottom:5px;'>ГРАФІК ІНСОЛЯЦІЇ (W/m²)</p>", unsafe_allow_html=True)
            chart_data = df_today.set_index('Time')[['Radiation']]
            st.area_chart(chart_data, color="#FFD700", height=180)

        st.markdown("---")

        # 3. ТАЙМЛАЙН ДОБИ (Сучасно і читабельно)
        st.write("📅 **Прогноз по годинах**")
        
        # Вибираємо ключові години для економії місця (кожні 2 години)
        display_hours = df_today[df_today['Time'].dt.hour.isin([8, 10, 12, 14, 16, 18, 20])]
        
        cols = st.columns(len(display_hours))
        for i, (idx, row) in enumerate(display_hours.iterrows()):
            with cols[i]:
                st.markdown(f"""
                    <div style='text-align: center; background: rgba(255,255,255,0.03); padding: 10px; border-radius: 10px;'>
                        <div style='font-size: 12px; color: gray;'>{row['Time'].strftime('%H:%M')}</div>
                        <div style='font-size: 24px; margin: 5px 0;'>{get_weather_icon(row['Clouds'], row['Rain'])}</div>
                        <div style='font-weight: bold;'>{row['Temp']:.0f}°</div>
                        <div style='font-size: 10px; color: #FFD700;'>{row['Radiation']:.0f}W</div>
                    </div>
                """, unsafe_allow_html=True)
        
        # 4. РЕЗЮМЕ ДНЯ
        st.markdown("<br>", unsafe_allow_html=True)
        m1, m2, m3 = st.columns(3)
        m1.metric("ПІК СОНЦЯ", f"{df_today['Radiation'].max():.0f} W/m²")
        m2.metric("СЕРЕДНЯ ХМАРНІСТЬ", f"{df_today['Clouds'].mean():.0f}%")
        m3.metric("ОПАДИ", f"{df_today['Rain'].sum():.1f} мм")

    else:
        st.info("🕒 Дані завантажуються...")
