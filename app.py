import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import time

# 1. Налаштування сторінки
st.set_page_config(page_title="Solar AI Nikopol v3.2", layout="wide", initial_sidebar_state="collapsed")

# 2. Стилізація інтерфейсу
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .ai-card { background: rgba(241, 196, 15, 0.05); border: 1px solid #f1c40f; border-radius: 10px; padding: 20px; }
    h1 { color: #ffffff; font-weight: 300; }
    </style>
    """, unsafe_allow_html=True)

# 3. Функція отримання метеоданих (з опадами та архівом)
@st.cache_data(ttl=600)
def get_weather_data():
    # Запитуємо: радіацію, хмарність, температуру та опади (ймовірність + кількість мм)
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation_probability,precipitation&timezone=auto&past_days=7&forecast_days=3"
    try:
        res = requests.get(url).json()
        h = res['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m'],
            'Rain_Prob': h['precipitation_probability'],
            'Rain_mm': h['precipitation']
        })
        
        # --- МОДЕЛЬ v3.0 TURBO (Корекція на основі факту 12.03) ---
        # Збільшено базовий ККД (0.00115) та зменшено вплив хмар (0.2)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00115 * (1 - df['Clouds']/100 * 0.2)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except:
        return None

# --- ЗАВАНТАЖЕННЯ ДАНИХ ---
df_all = get_weather_data()
df_fact = None
try:
    v_tag = int(time.time() / 60)
    # Пряме посилання на ваш Public репозиторій
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
except:
    pass

# --- ВЕРХНІЙ БЛОК: ОПЕРАТИВНИЙ МОНІТОРИНГ ---
st.title("☀️ Solar AI Monitor: Nikopol v3.2")

if df_all is not None:
    now = datetime.now()
    today_date = now.date()
    df_today = df_all[df_all['Time'].dt.date == today_date]
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Прогноз на сьогодні", f"{df_today['Power_MW'].sum():.1f} MWh")
    with col2:
        temp_now = df_today.iloc[now.hour]['Temp'] if now.hour < len(df_today) else 0
        st.metric("Температура", f"{temp_now}°C")
    with col3:
        rain_now = df_today.iloc[now.hour]['Rain_Prob'] if now.hour < len(df_today) else 0
        st.metric("Ймовірність опадів", f"{rain_now}%")
    with col4:
        st.metric("Статус СЕС", "11.4 MW Online")

    # Графік прогнозу (Майбутнє)
    df_future = df_all[df_all['Time'] >= pd.Timestamp(today_date)]
    
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    
    # 1. Золота гора (Прогноз)
    fig1.add_trace(go.Scatter(x=df_future['Time'], y=df_future['Power_MW'], name="Прогноз (MW)", fill='tozeroy', line=dict(color='#f1c40f', width=4)))
    
    # 2. Температура (Пунктир)
    fig1.add_trace(go.Scatter(x=df_future['Time'], y=df_future['Temp'], name="Темп (°C)", line=dict(color='#e74c3c', width=1, dash='dot')), secondary_y=True)
    
    # 3. Опади (Сині бари)
    fig1.add_trace(go.Bar(x=df_future['Time'], y=df_future['Rain_mm'], name="Опади (мм)", marker_color='rgba(0, 120, 255, 0.4)'))

    fig1.update_layout(template="plotly_dark", title="План генерації та метеоумови (3 дні)", height=450, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig1, use_container_width=True)

st.markdown("---")

# --- НИЖНІЙ БЛОК: АНАЛІТИКА ТА КОРЕКЦІЯ ШІ ---
if df_fact is not None and df_all is not None:
    st.header("📉 Аналіз точності та корекція ШІ")
    last_f_date = df_fact['Time'].dt.date.max()
    
    df_p_comp = df_all[df_all['Time'].dt.date == last_f_date]
    df_f_comp = df_fact[df_fact['Time'].dt.date == last_f_date]
    
    if not df_p_comp.empty and not df_f_comp.empty:
        c_graph, c_ai = st.columns([2, 1])
        with c_graph:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=df_p_comp['Time'], y=df_p_comp['Power_MW'], name="План (Модель)", line=dict(color='rgba(241, 196, 15, 0.4)', dash='dot')))
            fig2.add_trace(go.Scatter(x=df_f_comp['Time'], y=df_f_comp['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#e74c3c', width=3)))
            fig2.update_layout(template="plotly_dark", title=f"Аналіз за {last_f_date}", height=400)
            st.plotly_chart(fig2, use_container_width=True)
            
        with c_ai:
            st.markdown("<div class='ai-card'>", unsafe_allow_html=True)
            st.subheader("🤖 Вердикт ШІ")
            p_s, f_s = df_p_comp['Power_MW'].sum(), df_f_comp['Fact_MW'].sum()
            acc = (1 - abs(p_s - f_s)/p_s)*100 if p_s > 0 else 0
            st.write(f"**Точність моделі v3.0:** {acc:.1f}%")
            st.write(f"**Відхилення:** {f_s - p_s:.2f} MWh")
            st.markdown("---")
            if acc >= 90:
                st.success("✅ Модель адаптована успішно.")
            else:
                st.warning("⚠️ Потрібна подальша калібровка ваг.")
            st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Очікуємо нові дані для аналізу.")

st.markdown("<div style='text-align: right; color: gray; font-size: 10px;'>System v3.2 | Powered by Nikopol Solar AI</div>", unsafe_allow_html=True)
