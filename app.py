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
    # 1. ОСНОВНІ МЕТРИКИ
    m1, m2, m3 = st.columns(3)
    with m1: 
        st.metric("ШІ ПЛАН (СЬОГОДНІ)", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:.2f}x bias")
    with m2: 
        t_now = df_today[df_today['Time'].dt.hour == now_ua.hour]['Temp'].values[0] if not df_today.empty else 0
        st.metric("ТЕМПЕРАТУРА", f"{t_now}°C")
    with m3: 
        st.metric("СТАТУС СЕС", "11.4 MW Online")

    # 2. ВЕЛИКИЙ ГРАФІК ПРОГНОЗУ (На сьогодні-завтра)
    st.subheader("🚀 Оперативний план генерації (Прогноз)")
    fig_main = go.Figure()
    df_future = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(48)
    fig_main.add_trace(go.Scatter(x=df_future['Time'], y=df_future['Power_MW'], 
                                 name="План ШІ", fill='tozeroy', 
                                 line=dict(color='#00ff7f', width=3)))
    fig_main.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark")
    st.plotly_chart(fig_main, use_container_width=True)

    # 3. ЗОНА НАВЧАННЯ (Факт vs План)
    if df_fact is not None:
        st.markdown("---")
        st.subheader("🧠 Аналіз точності та навчання ШІ (Останні 3 дні)")
        
        # Об'єднуємо дані для порівняння
        df_compare = pd.merge(df_fact, df_all[['Time', 'Base_MW']], on='Time', how='left')
        df_compare['Plan_MW'] = df_compare['Base_MW'] * ai_bias
        
        # Вибираємо останні 3-4 дні для порівняння
        df_hist = df_compare.tail(96) 
        
        fig_study = go.Figure()
        # Лінія Факту (АСКОЕ)
        fig_study.add_trace(go.Scatter(x=df_hist['Time'], y=df_hist['Fact_MW'], 
                                      name="ФАКТ (АСКОЕ)", line=dict(color='#ff4b4b', width=4)))
        # Лінія Плану (який був побудований ШІ)
        fig_study.add_trace(go.Scatter(x=df_hist['Time'], y=df_hist['Plan_MW'], 
                                      name="ПЛАН ШІ", line=dict(color='rgba(255,255,255,0.4)', width=2, dash='dot')))
        
        fig_study.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), 
                               template="plotly_dark", hovermode="x unified")
        st.plotly_chart(fig_study, use_container_width=True)

        # Розрахунок дельти за вчора
        yesterday = (now_ua - pd.Timedelta(days=1)).date()
        df_yest = df_compare[df_compare['Time'].dt.date == yesterday]
        if not df_yest.empty:
            yest_fact = df_yest['Fact_MW'].sum()
            yest_plan = df_yest['Plan_MW'].sum()
            error = ((yest_fact - yest_plan) / yest_fact * 100) if yest_fact > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            c1.write(f"📊 Факт за вчора: **{yest_fact:.1f} MWh**")
            c2.write(f"📉 План за вчора: **{yest_plan:.1f} MWh**")
            c3.info(f"🎯 Відхилення: **{error:.1f}%**")

with tab2:
    if df_today is not None and not df_today.empty:
        # 1. ЗАГОЛОВОК (Центруємо)
        f_date = df_today['Time'].dt.date.iloc[0].strftime("%d.%m.%Y")
        st.markdown(f"<h1 style='text-align: center; margin-bottom: 30px;'>📅 Прогноз на сьогодні: <span style='color: #FFD700;'>{f_date}</span></h1>", unsafe_allow_html=True)
        
        now_hour = datetime.now(UA_TZ).hour
        current_data = df_today[df_today['Time'].dt.hour == now_hour].iloc[0] if now_hour < len(df_today) else df_today.iloc[0]

        # 2. ОСНОВНИЙ БЛОК
        col_info, col_chart = st.columns([1.2, 2])

        with col_info:
            # Створюємо єдину стильну картку для поточних даних
            icon = get_weather_icon(current_data['Clouds'], current_data['Rain'])
            st.markdown(f"""
                <div style='background: rgba(255, 255, 255, 0.05); padding: 25px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.1); text-align: center;'>
                    <p style='font-size: 80px; margin: 0;'>{icon}</p>
                    <div style='display: flex; justify-content: space-around; margin-top: 10px;'>
                        <div>
                            <p style='color: gray; font-size: 14px; margin: 0;'>ТЕМПЕРАТУРА</p>
                            <p style='font-size: 32px; font-weight: bold; margin: 0;'>{current_data['Temp']:.0f}°C</p>
                        </div>
                        <div>
                            <p style='color: gray; font-size: 14px; margin: 0;'>ХМАРНІСТЬ</p>
                            <p style='font-size: 32px; font-weight: bold; margin: 0;'>{current_data['Clouds']:.0f}%</p>
                        </div>
                    </div>
                    <hr style='border: 0; border-top: 1px solid rgba(255,255,255,0.1); margin: 20px 0;'>
                    <div style='display: flex; justify-content: space-around;'>
                        <div>
                            <p style='color: gray; font-size: 14px; margin: 0;'>ЕНЕРГІЯ НЕБА</p>
                            <p style='font-size: 28px; font-weight: bold; color: #FFD700; margin: 0;'>{current_data['Radiation']:.0f} <span style='font-size: 14px;'>W/m²</span></p>
                        </div>
                        <div>
                            <p style='color: gray; font-size: 14px; margin: 0;'>ОПАДИ</p>
                            <p style='font-size: 28px; font-weight: bold; color: #3498db; margin: 0;'>{current_data['Rain']:.1f} <span style='font-size: 14px;'>мм</span></p>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

        with col_chart:
            # Графік у рамці (через контейнер Streamlit)
            with st.container(border=True):
                st.write("📈 **Графік сонячної активності**")
                chart_data = df_today.set_index('Time')[['Radiation']]
                st.area_chart(chart_data, color="#FFD700", height=275)

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. ТАЙМЛАЙН (Повертаємо рамки-картки)
        st.write("🕒 **Ключові години доби:**")
        t_cols = st.columns(7)
        display_hours = df_today[df_today['Time'].dt.hour.isin([8, 10, 12, 14, 16, 18, 20])]
        
        for i, (idx, row) in enumerate(display_hours.iterrows()):
            with t_cols[i]:
                # Кожна година в окремій маленькій рамці
                st.markdown(f"""
                    <div style='background: rgba(255, 255, 255, 0.03); padding: 10px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.07); text-align: center;'>
                        <p style='font-size: 12px; color: gray; margin: 0;'>{row['Time'].strftime('%H:%M')}</p>
                        <p style='font-size: 24px; margin: 5px 0;'>{get_weather_icon(row['Clouds'], row['Rain'])}</p>
                        <p style='font-size: 18px; font-weight: bold; margin: 0;'>{row['Temp']:.0f}°</p>
                    </div>
                """, unsafe_allow_html=True)
