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

# Стилізація CSS
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 700; }
    .stPlotlyChart { border-radius: 15px; border: 1px solid rgba(128,128,128,0.2); }
    .footer { position: fixed; bottom: 10px; right: 20px; color: gray; font-size: 11px; z-index: 1000; text-align: right; }
    .status-tag { background: rgba(128,128,128,0.1); padding: 5px 15px; border-radius: 20px; border: 1px solid rgba(128,128,128,0.2); font-size: 13px; }
    
    /* Прогрес-бар ШІ */
    .progress-bg { background: rgba(128,128,128,0.2); border-radius: 10px; height: 8px; width: 120px; display: inline-block; margin-left: 10px; vertical-align: middle; }
    .progress-fill { background: #00ff7f; height: 100%; border-radius: 10px; }
    
    /* Горизонтальний скрол */
    .scroll-wrapper {
        display: flex !important;
        flex-direction: row !important;
        overflow-x: auto !important;
        gap: 15px;
        padding: 10px 5px;
        width: 100%;
    }
    .weather-card {
        flex: 0 0 auto !important;
        width: 140px;
        background: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 15px;
        padding: 15px;
        text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# 2. ФУНКЦІЇ ДАНИХ
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

# 3. ЛОГІКА ШІ
df_all = get_weather_data()
df_fact = None
ai_bias, last_update, days_learned = 1.0, "Немає даних", 0

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

# 4. ШАПКА
col_l, col_r = st.columns([1, 4])
with col_l:
    st.image("https://www.nzf.com.ua/img/logo.gif", width=120)
with col_r:
    st.title("SkyGrid: Solar AI Monitor Nikopol")
    prog_val = min(days_learned / 365 * 100, 100)
    st.markdown(f"""
        <div style='display:flex; flex-wrap:wrap; gap:10px; align-items:center;'>
            <span class='status-tag'>📅 Дані: <b>{last_update}</b></span>
            <span class='status-tag'>🧠 Досвід ШІ: <b>{days_learned} днів</b></span>
            <div style='display: inline-block;'>
                <div class='progress-bg'><div class='progress-fill' style='width:{prog_val}%;'></div></div>
            </div>
        </div>
    """, unsafe_allow_html=True)

# 5. ВКЛАДКИ
tab_main, tab_weather = st.tabs(["🚀 Моніторинг", "🌦 Прогноз погоди"])

with tab_main:
    if df_all is not None:
        now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
        df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        with m1: st.metric("План (Сьогодні)", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:.2f}x bias")
        with m2: 
            cur_h = now_ua.hour
            t_row = df_today[df_today['Time'].dt.hour == cur_h]
            t_now = t_row['Temp'].values[0] if not t_row.empty else 0
            st.metric("Температура", f"{t_now}°C")
        with m3: st.metric("Потужність", "11.4 MW Online")

        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(72).copy()
        fig1.add_trace(go.Bar(x=df_f['Time'], y=df_f['Rain'], name="Опади (mm)", marker_color='rgba(0, 120, 255, 0.3)'))
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="ШІ План (MW)", fill='tozeroy', line=dict(color='#2ecc71', width=3), fillcolor='rgba(46, 204, 113, 0.2)'))
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Temp'], name="Темп (°C)", line=dict(color='#e74c3c', width=1.5, dash='dot')), secondary_y=True)
        fig1.update_layout(height=480, margin=dict(l=20, r=20, t=50, b=20), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig1, use_container_width=True)

with tab_weather:
    st.subheader("Погодинний прогноз (Сьогодні)")
    
    # ЗБИРАЄМО ВСЕ В ОДИН РЯДОК БЕЗ ЗАЙВИХ ПРОБІЛІВ
    cards = ""
    for _, row in df_today.iterrows():
        w_dir = get_wind_dir(row['WindDir'])
        cards += (
            f'<div class="weather-card">'
            f'<div style="font-weight: bold; color: #1E3A8A; font-size: 14px;">{row["Time"].strftime("%H:%M")}</div>'
            f'<div style="font-size: 22px; font-weight: bold; margin: 8px 0;">{row["Temp"]:.1f}°</div>'
            f'<div style="font-size: 11px; color: #555; line-height: 1.5; text-align: left;">'
            f'☁️ Хмарність: <b>{row["Clouds"]}%</b><br>'
            f'💧 Опади: <b>{row["Rain"]} мм</b><br>'
            f'💨 Вітер: <b>{row["WindSp"]} м/с {w_dir}</b>'
            f'</div></div>'
        )
    
    # ВИВОДИМО ЯК ЄДИНИЙ КОНТЕЙНЕР
    st.markdown(f'<div class="scroll-wrapper">{cards}</div>', unsafe_allow_html=True)
    
    st.markdown("---")
    st.subheader("Прогноз на 10 днів")
    df_10d = df_all.groupby(df_all['Time'].dt.date).agg({'Temp':['min','max'], 'Power_MW':'sum', 'Rain':'sum', 'Clouds':'mean'})
    d_cols = st.columns(5)
    for idx, (date, row) in enumerate(df_10d.iterrows()):
        with d_cols[idx % 5]:
            st.markdown(f"""
            <div style='border: 1px solid rgba(128,128,128,0.2); border-radius:15px; padding:15px; margin-bottom:15px; background: rgba(255,255,255,0.05);'>
                <h4 style='margin:0; color:#1E3A8A;'>{date.strftime('%d.%m')}</h4>
                <p style='margin:10px 0; font-size:20px;'><b>{row[('Temp','max')]:.1f}°</b> <span style='color:gray; font-size:14px;'>/ {row[('Temp','min')]:.1f}°</span></p>
                <div style='font-size:12px; line-height:1.6;'>
                    <span style='color:#2ecc71;'>🔋 {row[('Power_MW','sum')]:.1f} MWh</span><br>
                    <span style='color:blue;'>💧 Опади: {row[('Rain','sum')]:.1f} мм</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

st.markdown(f"<div class='footer'>Developed by Sergii Kolesnyk | SkyGrid v3.6.4<br>АТ 'НЗФ' © 2026</div>", unsafe_allow_html=True)
