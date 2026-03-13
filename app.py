import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Solar AI Nikopol v3.3", layout="wide", initial_sidebar_state="collapsed")

# 1. СТИЛІЗАЦІЯ
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .ai-card { background: rgba(0, 255, 127, 0.05); border: 1px solid #00ff7f; border-radius: 10px; padding: 20px; }
    </style>
    """, unsafe_allow_html=True)

# 2. ОТРИМАННЯ МЕТЕОДАНИХ
@st.cache_data(ttl=600)
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation&timezone=auto&past_days=7&forecast_days=3"
    try:
        res = requests.get(url).json()
        h = res['hourly']
        return pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m'],
            'Rain': h['precipitation']
        })
    except: return None

# --- ЗАВАНТАЖЕННЯ ТА АДАПТАЦІЯ ШІ ---
df_all = get_weather_data()
df_fact = None
ai_bias = 1.0  # Базовий коефіцієнт (без корекції)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    
    # --- МОЗОК ШІ: АВТОМАТИЧНА КОРЕКЦІЯ ---
    last_date = df_fact['Time'].dt.date.max()
    f_day = df_fact[df_fact['Time'].dt.date == last_date]
    p_day = df_all[df_all['Time'].dt.date == last_date]
    
    if not f_day.empty and not p_day.empty:
        # Розрахунок похибки вчорашнього дня
        actual_sum = f_day['Fact_MW'].sum()
        # Базовий прогноз (без поправки)
        base_pred_sum = (p_day['Radiation'] * 11.4 * 0.00115 * (1 - p_day['Clouds']/100 * 0.2)).sum()
        
        if base_pred_sum > 0:
            ai_bias = actual_sum / base_pred_sum  # Наскільки помилився ШІ
except: pass

# Застосування корекції до всього прогнозу
if df_all is not None:
    # ШІ множить базову модель на свій вирахуваний коефіцієнт ai_bias
    df_all['Power_MW'] = (df_all['Radiation'] * 11.4 * 0.00115 * (1 - df_all['Clouds']/100 * 0.2)) * ai_bias
    df_all.loc[df_all['Power_MW'] < 0, 'Power_MW'] = 0

# --- ВЕРХНІЙ БЛОК ---
st.title("☀️ Solar AI Monitor: Автопілот v3.3")

if df_all is not None:
    now = datetime.now()
    df_today = df_all[df_all['Time'].dt.date == now.date()]
    
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Адаптований прогноз", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:+.2f}x коеф.")
    with c2: st.metric("Температура", f"{df_today.iloc[now.hour]['Temp']}°C")
    with c3: st.metric("Потужність", "11.4 MW")

    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    df_f = df_all[df_all['Time'] >= pd.Timestamp(now.date())]
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="Прогноз ШІ (з корекцією)", fill='tozeroy', line=dict(color='#00ff7f', width=4)))
    fig1.update_layout(template="plotly_dark", height=450)
    st.plotly_chart(fig1, use_container_width=True)

# --- НИЖНІЙ БЛОК: ЗВІТ ШІ ---
if df_fact is not None:
    st.markdown("---")
    st.header("🤖 Аналітика та Самонавчання")
    
    col_a, col_b = st.columns([2, 1])
    with col_a:
        # Порівняння за вчора
        last_date = df_fact['Time'].dt.date.max()
        df_p_comp = df_all[df_all['Time'].dt.date == last_date]
        df_f_comp = df_fact[df_fact['Time'].dt.date == last_date]
        
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df_p_comp['Time'], y=df_p_comp['Power_MW'], name="ШІ (після навчання)", line=dict(color='#00ff7f', width=2, dash='dot')))
        fig2.add_trace(go.Scatter(x=df_f_comp['Time'], y=df_f_comp['Fact_MW'], name="Реальний Факт", line=dict(color='#e74c3c', width=3)))
        fig2.update_layout(template="plotly_dark", title=f"Як ШІ підлаштувався під {last_date}", height=350)
        st.plotly_chart(fig2, use_container_width=True)

    with col_b:
        st.markdown(f"<div class='ai-card'>", unsafe_allow_html=True)
        st.subheader("💡 Вердикт Автопілота")
        st.write(f"**Поточний коеф. навчання:** {ai_bias:.3f}")
        
        if ai_bias > 1:
            st.success(f"ШІ виявив, що СЕС працює ефективніше прогнозу. Потужність штучно піднята на {int((ai_bias-1)*100)}%.")
        elif ai_bias < 1:
            st.warning(f"ШІ знизив прогноз на {int((1-ai_bias)*100)}% через виявлені втрати.")
        
        st.info("Корекція застосовується автоматично до майбутніх 72 годин.")
        st.markdown("</div>", unsafe_allow_html=True)
