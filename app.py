import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import time
import pytz
from io import BytesIO

st.set_page_config(page_title="Solar AI Nikopol v3.5.1", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 1. СТИЛІЗАЦІЯ
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .ai-card { background: rgba(0, 255, 127, 0.05); border: 1px solid #00ff7f; border-radius: 10px; padding: 20px; }
    .stDownloadButton button { width: 100%; background-color: #00ff7f !important; color: black !important; font-weight: bold !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. ОТРИМАННЯ МЕТЕОДАНИХ (З ФІНАЛЬНИМ ЗСУВОМ ЧАСУ)
@st.cache_data(ttl=600)
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation&timezone=auto&past_days=7&forecast_days=3"
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
        
        # --- ФІНАЛЬНА КОРЕКЦІЯ ЧАСУ ---
        # 1. Переводимо в київський час
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None)
        # 2. Примусово зсуваємо на 2 години назад, щоб пік став о 12:00
        df['Time'] = df['Time'] - pd.Timedelta(hours=2)
        
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00115 * (1 - df['Clouds']/100 * 0.2)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

# --- АДАПТАЦІЯ ШІ ---
df_all = get_weather_data()
df_fact = None
ai_bias = 1.0 

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    
    last_date = df_fact['Time'].dt.date.max()
    f_day = df_fact[df_fact['Time'].dt.date == last_date]
    p_day = df_all[df_all['Time'].dt.date == last_date]
    
    if not f_day.empty and not p_day.empty:
        actual_sum = f_day['Fact_MW'].sum()
        base_pred = (p_day['Radiation'] * 11.4 * 0.00115 * (1 - p_day['Clouds']/100 * 0.2)).sum()
        if base_pred > 0: ai_bias = actual_sum / base_pred
except: pass

if df_all is not None:
    df_all['Power_MW'] = df_all['Power_MW'] * ai_bias

# --- ІНТЕРФЕЙС ---
st.title("☀️ Solar AI Monitor: Nikopol v3.5.1")

if df_all is not None:
    now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
    df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
    
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("План (Адаптований)", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:.2f}x")
    with c2: 
        # Визначаємо поточну годину для метрики
        current_hour = now_ua.hour
        temp_val = df_today[df_today['Time'].dt.hour == current_hour]['Temp'].values[0] if not df_today[df_today['Time'].dt.hour == current_hour].empty else 0
        st.metric("Температура", f"{temp_val}°C")
    with c3: st.metric("Статус", "Автопілот Активний")

    # Графік
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].copy()

    fig1.add_trace(go.Bar(x=df_f['Time'], y=df_f['Rain'], name="Опади (мм)", marker_color='rgba(0, 150, 255, 0.4)'))
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="ШІ Прогноз", fill='tozeroy', line=dict(color='#00ff7f', width=3), fillcolor='rgba(0, 255, 127, 0.2)'))
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Temp'], name="Темп (°C)", line=dict(color='#ff4b4b', width=1, dash='dot')), secondary_y=True)

    fig1.update_layout(template="plotly_dark", height=450, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig1, use_container_width=True)

    # Excel Експорт
    df_excel = df_f[['Time', 'Power_MW', 'Temp', 'Rain', 'Clouds']].head(72).copy()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_excel.to_excel(writer, index=False, sheet_name='Plan')
    st.download_button(label="📥 Скачати Excel План", data=output.getvalue(), file_name=f"Solar_AI_Plan.xlsx")

# Аналітика
if df_fact is not None:
    st.markdown("---")
    last_date = df_fact['Time'].dt.date.max()
    st.subheader(f"🤖 Аналіз точності за {last_date}")
    df_p_comp = df_all[df_all['Time'].dt.date == last_date]
    df_f_comp = df_fact[df_fact['Time'].dt.date == last_date]
    
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df_p_comp['Time'], y=df_p_comp['Power_MW'], name="ШІ Корекція", line=dict(color='#00ff7f', dash='dot')))
    fig2.add_trace(go.Scatter(x=df_f_comp['Time'], y=df_f_comp['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#e74c3c', width=3)))
    fig2.update_layout(template="plotly_dark", height=350)
    st.plotly_chart(fig2, use_container_width=True)
