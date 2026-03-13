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

# 2. ДИЗАЙНЕРСЬКА СТИЛІЗАЦІЯ (Збільшені шрифти та іконки)
st.markdown("""
    <style>
    .block-container { padding: 1rem 2rem; }
    
    /* Прогрес-бар ШІ */
    .progress-bg { background: rgba(255,255,255,0.1); border-radius: 10px; height: 12px; width: 180px; display: inline-block; vertical-align: middle; overflow: hidden; margin-left: 10px; border: 1px solid rgba(0,255,127,0.3); }
    .progress-fill { background: linear-gradient(90deg, #00ff7f, #00d4ff); height: 100%; border-radius: 10px; }
    
    /* Горизонтальний ряд карток (Почасово) */
    .weather-row {
        display: flex !important;
        flex-direction: row !important;
        justify-content: space-between !important;
        width: 100%;
        gap: 6px;
        margin: 15px 0;
    }
    .weather-card-industrial {
        flex: 1;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(0, 212, 255, 0.3);
        border-radius: 12px;
        padding: 12px 5px;
        text-align: center;
        min-width: 0;
        transition: transform 0.2s;
    }
    .w-time-ind { font-size: 14px; color: #00d4ff; font-weight: bold; margin-bottom: 5px; }
    .w-temp-ind { font-size: 22px; font-weight: 900; color: #ffffff; margin: 5px 0; }
    .w-info-ind { font-size: 12px; color: #bbb; line-height: 1.4; font-weight: 500; }
    .w-icon-ind { font-size: 18px; margin-bottom: 2px; }
    
    /* 10 днів (Великі блоки) */
    .day-grid {
        display: grid;
        grid-template-columns: repeat(10, 1fr);
        gap: 10px;
        margin-top: 10px;
    }
    .day-card-industrial {
        background: linear-gradient(145deg, rgba(255,255,255,0.07), rgba(255,255,255,0.02));
        border: 1px solid rgba(0, 212, 255, 0.4);
        border-radius: 15px;
        padding: 15px 10px;
        text-align: center;
    }
    .day-date { color: #00d4ff; font-size: 16px; font-weight: bold; margin-bottom: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 5px; }
    .day-temp { font-size: 26px; font-weight: 800; color: #fff; margin: 8px 0; }
    .day-gen { font-size: 14px; color: #00ff7f; font-weight: bold; }
    
    .footer { position: fixed; bottom: 10px; right: 20px; color: gray; font-size: 12px; }
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
ai_bias, last_update, days_learned = 1.0, "...", 0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    last_date = df_fact['Time'].dt.date.max()
    last_update = last_date.strftime("%d.%m.%Y")
    days_learned = len(df_fact['Time'].dt.date.unique())
    # Bias...
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
col_logo, col_title = st.columns([0.6, 5])
with col_logo:
    st.image("https://www.nzf.com.ua/img/logo.gif", width=100)
with col_title:
    prog_val = min(days_learned / 365 * 100, 100)
    st.markdown(f"""
        <div style='display:flex; justify-content:space-between; align-items:center; padding-top:10px;'>
            <h1 style='margin:0; font-size:32px; color:white;'>SkyGrid: Solar AI Monitor Nikopol</h1>
            <div style='display:flex; gap:15px; align-items:center;'>
                <span class='status-tag' style='font-size:16px;'>📅 <b>{last_update}</b></span>
                <span class='status-tag' style='font-size:16px;'>🧠 Досвід ШІ: <b>{days_learned} днів</b> <div class='progress-bg'><div class='progress-fill' style='width:{prog_val}%;'></div></div></span>
            </div>
        </div>
    """, unsafe_allow_html=True)

# 6. ВКЛАДКИ
tab_main, tab_weather = st.tabs(["🚀 МОНІТОРИНГ", "🌦 ПРОГНОЗ ПОГОДИ"])

with tab_main:
    if df_all is not None:
        now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
        df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        with m1: st.metric("ПЛАН НА СЬОГОДНІ", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:.2f}x bias")
        with m2: 
            cur_h = now_ua.hour
            t_row = df_today[df_today['Time'].dt.hour == cur_h]
            t_now = t_row['Temp'].values[0] if not t_row.empty else 0
            st.metric("ПОТОЧНА ТЕМПЕРАТУРА", f"{t_now}°C")
        with m3: st.metric("СТАТУС МЕРЕЖІ", "11.4 MW Online", delta_color="normal")

        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(72).copy()
        fig1.add_trace(go.Bar(x=df_f['Time'], y=df_f['Rain'], name="Опади (мм)", marker_color='rgba(0, 150, 255, 0.4)'))
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="ШІ План (МВт)", fill='tozeroy', line=dict(color='#00ff7f', width=4)))
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Temp'], name="Темп (°C)", line=dict(color='#ff4b4b', width=2, dash='dot')), secondary_y=True)
        fig1.update_layout(height=400, margin=dict(l=10, r=10, t=30, b=10), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig1, use_container_width=True)

with tab_weather:
    st.markdown("### 🕒 ПОГОДИННИЙ ПРОГНОЗ (24 ГОДИНИ)")
    
    # Створюємо 24 великі картки в один ряд
    cards_html = '<div class="weather-row">'
    for _, row in df_today.iterrows():
        w_dir = get_wind_dir(row['WindDir'])
        cards_html += (
            f'<div class="weather-card-industrial">'
            f'<div class="w-time-ind">{row["Time"].strftime("%H:%M")}</div>'
            f'<div class="w-temp-ind">{row["Temp"]:.1f}°</div>'
            f'<div class="w-info-ind">'
            f'<div class="w-icon-ind">☁️ {row["Clouds"]}%</div>'
            f'<div class="w-icon-ind">💧 {row["Rain"]:.1f}</div>'
            f'<div style="font-size:10px; margin-top:3px;">{w_dir} {row["WindSp"]:.0f}м/с</div>'
            f'</div></div>'
        )
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 📅 ПРОГНОЗ НА 10 ДНІВ")
    
    df_10d = df_all.groupby(df_all['Time'].dt.date).agg({'Temp':['min','max'], 'Power_MW':'sum', 'Rain':'sum'})
    
    # Використовуємо HTML-грід для ідеального розміщення
    day_html = '<div class="day-grid">'
    for date, row in df_10d.iterrows():
        day_html += (
            f'<div class="day-card-industrial">'
            f'<div class="day-date">{date.strftime("%d.%m")}</div>'
            f'<div class="day-temp">{row[("Temp","max")]:.0f}°</div>'
            f'<div class="day-gen">🔋 {row[("Power_MW","sum")]:.1f}</div>'
            f'<div style="color:rgba(255,255,255,0.6); font-size:12px; margin-top:5px;">💧 {row[("Rain","sum")]:.1f} мм</div>'
            f'</div>'
        )
    day_html += '</div>'
    st.markdown(day_html, unsafe_allow_html=True)

st.markdown(f"<div class='footer'><b>Розробник:</b> Сергій Колесник | АТ 'НЗФ' © 2026</div>", unsafe_allow_html=True)
