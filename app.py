import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime
import time
import pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI Nikopol v3.7.8", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. НОВИЙ ГІБРИДНИЙ ДИЗАЙН (Data-Driven + Icons)
st.markdown("""
    <style>
    .block-container { padding: 1rem 1rem; }
    
    /* Прогрес-бар ШІ */
    .progress-bg { background: rgba(255,255,255,0.1); border-radius: 10px; height: 12px; width: 150px; display: inline-block; vertical-align: middle; overflow: hidden; margin-left: 10px; border: 1px solid rgba(0,255,127,0.3); }
    .progress-fill { background: linear-gradient(90deg, #00ff7f, #00d4ff); height: 100%; border-radius: 10px; }
    
    /* Почасовий прогноз */
    .weather-row { display: flex !important; flex-direction: row !important; justify-content: space-between !important; width: 100%; gap: 4px; margin: 10px 0; }
    .weather-card-industrial { flex: 1; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(0, 212, 255, 0.2); border-radius: 8px; padding: 8px 2px; text-align: center; min-width: 0; }
    
    /* 10 ДНІВ: ГІБРИДНИЙ ДИЗАЙН (Data-Driven) */
    .day-grid-fixed {
        display: grid;
        grid-template-columns: repeat(10, 1fr);
        gap: 8px;
        width: 100%;
        margin-top: 10px;
    }
    .day-card-hybrid { 
        background: #1e2124; 
        border: 1px solid #32383e; 
        border-radius: 12px; 
        padding: 12px 5px; 
        text-align: center;
        position: relative;
    }
    .day-date { color: #5dade2; font-size: 14px; font-weight: bold; margin-bottom: 5px; }
    .day-temp-max { font-size: 32px; font-weight: 800; color: #ffffff; line-height: 1; }
    .day-temp-min { font-size: 16px; color: #85929e; margin-bottom: 8px; }
    .day-icon { font-size: 24px; margin-bottom: 5px; }
    
    /* Шкала опадів (Data-Driven style) */
    .rain-bar-bg { background: #2c3e50; border-radius: 3px; height: 4px; width: 80%; margin: 5px auto; overflow: hidden; }
    .rain-bar-fill { background: #3498db; height: 100%; }
    
    .footer { position: fixed; bottom: 10px; right: 20px; color: gray; font-size: 11px; }
    </style>
    """, unsafe_allow_html=True)

# 3. ФУНКЦІЇ ДАНИХ
@st.cache_data(ttl=300)
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation&timezone=auto&past_days=7&forecast_days=10"
    try:
        res = requests.get(url).json()
        h = res['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m'],
            'Rain': h['precipitation']
        })
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None)
        df['Base_MW'] = df['Radiation'] * 11.4 * 0.00115 * (1 - df['Clouds']/100 * 0.2)
        return df
    except: return None

def get_weather_icon(clouds, rain):
    if rain > 0.5: return "🌧️"
    if clouds > 70: return "☁️"
    if clouds > 30: return "⛅"
    return "☀️"

# 4. ЛОГІКА ШІ
df_all = get_weather_data()
df_fact = None
ai_bias, last_update, days_learned = 1.0, "Оновлення", 0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    last_date = df_fact['Time'].dt.date.max()
    last_update = last_date.strftime("%d.%m.%Y")
    days_learned = len(df_fact['Time'].dt.date.unique())
    
    f_day = df_fact[df_fact['Time'].dt.date == last_date]
    p_day = df_all[df_all['Time'].dt.date == last_date] if df_all is not None else pd.DataFrame()
    if not f_day.empty and not p_day.empty:
        ai_bias = f_day['Fact_MW'].sum() / p_day['Base_MW'].sum() if p_day['Base_MW'].sum() > 0 else 1.0
except: pass

if df_all is not None:
    df_all['Power_MW'] = df_all['Base_MW'] * ai_bias

# 5. ШАПКА
col_logo, col_title = st.columns([0.6, 5])
with col_logo: st.image("https://www.nzf.com.ua/img/logo.gif", width=80)
with col_title:
    prog_val = min(days_learned / 365 * 100, 100)
    st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:center; padding-top:10px;'><h2 style='margin:0;'>SkyGrid: Solar AI Monitor Nikopol</h2><div style='display:flex; gap:15px; align-items:center;'><span style='font-size:14px;'>📅 АСКОЕ: <b>{last_update}</b></span><span style='font-size:14px;'>🧠 ШІ: <b>{days_learned} дн.</b> <div class='progress-bg'><div class='progress-fill' style='width:{prog_val}%;'></div></div></span></div></div>", unsafe_allow_html=True)

# 6. ВКЛАДКИ
tab_main, tab_weather = st.tabs(["🚀 МОНІТОРИНГ", "🌦 ПРОГНОЗ ПОГОДИ"])

with tab_main:
    if df_all is not None:
        now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
        df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
        m1, m2, m3 = st.columns(3)
        with m1: st.metric("ШІ ПЛАН (СЬОГОДНІ)", f"{df_today['Power_MW'].sum():.1f} MWh", f"Bias: {ai_bias:.2f}x")
        with m2: 
            t_now = df_today[df_today['Time'].dt.hour == now_ua.hour]['Temp'].values[0] if not df_today.empty else 0
            st.metric("ТЕМПЕРАТУРА", f"{t_now}°C")
        with m3: st.metric("СТАТУС СЕС", "11.4 MW Online")

        # Графіки (Стислий формат)
        fig1 = go.Figure()
        df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(72)
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="План (МВт)", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
        fig1.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig1, use_container_width=True)

        if df_fact is not None:
            df_hist_fact = df_fact.tail(72)
            fig_learn = go.Figure()
            fig_learn.add_trace(go.Scatter(x=df_hist_fact['Time'], y=df_hist_fact['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#ff4b4b', width=3)))
            fig_learn.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_learn, use_container_width=True)

with tab_weather:
    st.markdown("### 🕒 ПОЧАСОВО (24 ГОД)")
    cards_html = '<div class="weather-row">'
    for _, row in df_today.iterrows():
        cards_html += f'<div class="weather-card-industrial"><div style="color:#5dade2;font-size:12px;">{row["Time"].strftime("%H:%M")}</div><div style="font-size:18px;font-weight:bold;">{row["Temp"]:.0f}°</div><div style="font-size:10px;color:#bbb;">{get_weather_icon(row["Clouds"], row["Rain"])}</div></div>'
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 📅 МЕТЕОПРОГНОЗ НА 10 ДНІВ")
    
    df_10d = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].groupby(df_all['Time'].dt.date).agg({'Temp':['min','max'], 'Clouds':'mean', 'Rain':'sum'}).head(10)
    
    day_html = '<div class="day-grid-fixed">'
    for date, row in df_10d.iterrows():
        icon = get_weather_icon(row[("Clouds","mean")], row[("Rain","sum")])
        rain_val = min(row[("Rain","sum")] * 10, 100) # Для візуалізації шкали
        day_html += f"""
        <div class="day-card-hybrid">
            <div class="day-date">{date.strftime("%d.%m")}</div>
            <div class="day-icon">{icon}</div>
            <div class="day-temp-max">{row[("Temp","max")]:.0f}°</div>
            <div class="day-temp-min">/{row[("Temp","min")]:.0f}°</div>
            <div class="rain-bar-bg"><div class="rain-bar-fill" style="width:{rain_val}%;"></div></div>
            <div style="font-size:10px; color:#85929e;">💧 {row[("Rain","sum")]:.1f}мм</div>
        </div>"""
    day_html += '</div>'
    st.markdown(day_html, unsafe_allow_html=True)

st.markdown(f"<div class='footer'><b>Розробник:</b> Сергій Колесник | АТ 'НЗФ' © 2026</div>", unsafe_allow_html=True)
