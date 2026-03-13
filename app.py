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
st.set_page_config(page_title="SkyGrid: Solar AI Nikopol v3.6.4", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. СТИЛІЗАЦІЯ (Фікс для вміщення на один екран)
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; padding-left: 1rem; padding-right: 1rem; }
    div[data-testid="stMetricValue"] { font-size: 1.5rem; font-weight: 700; }
    
    .status-tag { background: rgba(128,128,128,0.1); padding: 3px 10px; border-radius: 12px; border: 1px solid rgba(128,128,128,0.2); font-size: 12px; }
    
    /* Прогрес-бар ШІ */
    .progress-bg { background: rgba(128,128,128,0.2); border-radius: 6px; height: 6px; width: 100px; display: inline-block; vertical-align: middle; overflow: hidden; }
    .progress-fill { background: linear-gradient(90deg, #00ff7f, #00d4ff); height: 100%; border-radius: 6px; }
    
    /* Горизонтальний ряд карток (БЕЗ СКРОЛУ) */
    .weather-row {
        display: flex !important;
        justify-content: space-between !important;
        width: 100%;
        gap: 2px;
        margin: 10px 0;
    }
    .weather-card-mini {
        flex: 1;
        min-width: 0; /* Дозволяє стискатися */
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(0, 212, 255, 0.15);
        border-radius: 8px;
        padding: 5px 2px;
        text-align: center;
    }
    .w-time-mini { font-size: 11px; color: #00d4ff; font-weight: bold; }
    .w-temp-mini { font-size: 16px; font-weight: 800; color: #ffffff; margin: 2px 0; }
    .w-info-mini { font-size: 9px; color: #aaa; line-height: 1.1; }
    
    /* 10 днів у ряд */
    .day-card-mini {
        border: 1px solid rgba(0,212,255,0.2);
        border-radius: 10px;
        padding: 8px;
        background: rgba(255,255,255,0.03);
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# 3. ФУНКЦІЇ ДАНИХ
@st.cache_data(ttl=600)
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation,wind_speed_10m,wind_direction_10m&timezone=auto&forecast_days=10"
    try:
        res = requests.get(url).json()
        h = res['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m'],
            'Rain': h['precipitation'],
            'WindSp': h['wind_speed_10m'],
            'WindDir': h['wind_direction_10m']
        })
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None) - pd.Timedelta(hours=2)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00115 * (1 - df['Clouds']/100 * 0.2)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

def get_wind_dir(deg):
    dirs = ['Пн', 'ПнСх', 'Сх', 'ПдСх', 'Пд', 'ПдЗх', 'Зх', 'ПнЗх']
    return dirs[int((deg + 22.5) // 45) % 8]

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
    p_day = df_all[df_all['Time'].dt.date == last_date]
    if not f_day.empty and not p_day.empty:
        actual_sum = f_day['Fact_MW'].sum()
        base_pred = (p_day['Radiation'] * 11.4 * 0.00115 * (1 - p_day['Clouds']/100 * 0.2)).sum()
        if base_pred > 0: ai_bias = actual_sum / base_pred
except: pass

if df_all is not None:
    df_all['Power_MW'] = df_all['Power_MW'] * ai_bias

# 5. ШАПКА
col_logo, col_title = st.columns([0.5, 5])
with col_logo:
    st.image("https://www.nzf.com.ua/img/logo.gif", width=60)
with col_title:
    prog_val = min(days_learned / 365 * 100, 100)
    st.markdown(f"""
        <div style='display:flex; justify-content:space-between; align-items:center;'>
            <h3 style='margin:0;'>SkyGrid: Solar AI Monitor Nikopol</h3>
            <div style='display:flex; gap:10px; align-items:center;'>
                <span class='status-tag'>📅 {last_update}</span>
                <span class='status-tag'>🧠 ШІ: {days_learned} дн. <div class='progress-bg'><div class='progress-fill' style='width:{prog_val}%;'></div></div></span>
            </div>
        </div>
    """, unsafe_allow_html=True)

# 6. ВКЛАДКИ
tab_main, tab_weather = st.tabs(["🚀 Моніторинг", "🌦 Прогноз"])

# --- ВКЛАДКА 1 (БЕЗ ЗМІН) ---
with tab_main:
    if df_all is not None:
        now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
        df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
        m1, m2, m3 = st.columns(3)
        with m1: st.metric("План", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:.2f}x")
        with m2: 
            cur_h = now_ua.hour
            t_row = df_today[df_today['Time'].dt.hour == cur_h]
            t_now = t_row['Temp'].values[0] if not t_row.empty else 0
            st.metric("Темп.", f"{t_now}°C")
        with m3: st.metric("СЕС", "11.4 MW Online")

        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(72).copy()
        fig1.add_trace(go.Bar(x=df_f['Time'], y=df_f['Rain'], name="Опади", marker_color='rgba(0, 120, 255, 0.3)'))
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="ШІ План", fill='tozeroy', line=dict(color='#2ecc71', width=3)))
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Temp'], name="Темп", line=dict(color='#e74c3c', width=1.5, dash='dot')), secondary_y=True)
        fig1.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig1, use_container_width=True)

# --- ВКЛАДКА 2 (УЛЬТРАКОМПАКТНА) ---
with tab_weather:
    st.markdown("<p style='margin-bottom:2px; font-weight:bold;'>Почасовий прогноз (24 год) — Усе в один ряд:</p>", unsafe_allow_html=True)
    
    # Створюємо 24 картки в один ряд
    cards_html = '<div class="weather-row">'
    for _, row in df_today.iterrows():
        w_dir = get_wind_dir(row['WindDir'])
        cards_html += (
            f'<div class="weather-card-mini">'
            f'<div class="w-time-mini">{row["Time"].strftime("%H")}</div>'
            f'<div class="w-temp-mini">{row["Temp"]:.0f}°</div>'
            f'<div class="w-info-mini">☁️{row["Clouds"]}%<br>💧{row["Rain"]:.1f}<br>{w_dir}</div>'
            f'</div>'
        )
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)
    
    st.markdown("<p style='margin-top:5px; margin-bottom:2px; font-weight:bold;'>Прогноз на 10 днів:</p>", unsafe_allow_html=True)
    df_10d = df_all.groupby(df_all['Time'].dt.date).agg({'Temp':['min','max'], 'Power_MW':'sum', 'Rain':'sum'})
    
    d_cols = st.columns(10) # Усі 10 днів в один ряд!
    for idx, (date, row) in enumerate(df_10d.iterrows()):
        with d_cols[idx]:
            st.markdown(f"""
            <div class='day-card-mini'>
                <div style='color:#00d4ff; font-size:12px; font-weight:bold;'>{date.strftime('%d.%m')}</div>
                <div style='font-size:16px; margin:2px 0;'><b>{row[('Temp','max')]:.0f}°</b></div>
                <div style='font-size:10px; color:#00ff7f;'>🔋{row[('Power_MW','sum')]:.1f}</div>
                <div style='font-size:9px; color:blue;'>💧{row[('Rain','sum')]:.1f}</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown(f"<div class='footer'>Developed by Sergii Kolesnyk | АТ 'НЗФ' © 2026</div>", unsafe_allow_html=True)
