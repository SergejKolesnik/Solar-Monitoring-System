import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Solar AI Nikopol", layout="wide", initial_sidebar_state="collapsed")

# 1. Дизайн
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .ai-card { background: rgba(241, 196, 15, 0.05); border: 1px solid #f1c40f; border-radius: 10px; padding: 20px; margin-top: 20px; }
    </style>
    """, unsafe_allow_html=True)

# 2. Отримання даних (Архів за 7 днів + Прогноз на 3 дні)
def get_solar_data():
    # past_days=7 дозволяє нам завжди бачити "вчора" для будь-якого звіту АСКОЕ
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m&timezone=auto&past_days=7&forecast_days=3"
    try:
        res = requests.get(url).json()
        h = res['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m']
        })
        # Математична модель v2.6
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00092 * (1 - df['Clouds']/100 * 0.4)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

# --- ЗАВАНТАЖЕННЯ ---
df_all = get_solar_data()
df_fact = None
try:
    v_tag = int(time.time() / 30)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
except: pass

# --- БЛОК 1: ОПЕРАТИВНИЙ МОНІТОРИНГ (МАЙБУТНЄ) ---
st.title("☀️ Solar AI Monitor: Оперативне управління")

if df_all is not None:
    today_date = datetime.now().date()
    df_today = df_all[df_all['Time'].dt.date == today_date]
    
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Прогноз на сьогодні", f"{df_today['Power_MW'].sum():.1f} MWh")
    with col2: 
        hour_idx = datetime.now().hour
        temp_now = df_today.iloc[hour_idx]['Temp'] if not df_today.empty else 0
        st.metric("Температура Нікополь", f"{temp_now}°C")
    with col3: st.metric("Статус СЕС", "11.4 MW Online")

    fig1 = go.Figure()
    # Відображаємо тільки сьогоднішній день і майбутнє
    df_future = df_all[df_all['Time'] >= pd.Timestamp(today_date)]
    fig1.add_trace(go.Scatter(x=df_future['Time'], y=df_future['Power_MW'], name="План (MW)", fill='tozeroy', line=dict(color='#f1c40f', width=4)))
    fig1.update_layout(template="plotly_dark", title="Майбутня генерація (сьогодні + 2 дні)", height=400)
    st.plotly_chart(fig1, use_container_width=True)

st.markdown("---")

# --- БЛОК 2: АНАЛІТИКА ТА КОРЕКЦІЯ ШІ (МИНУЛЕ) ---
if df_fact is not None and df_all is not None:
    st.header("📉 Ретроспективний аналіз та корекція ШІ")
    
    # Автоматично беремо останню дату, яка з'явилася у звіті АСКОЕ
    last_f_date = df_fact['Time'].dt.date.max()
    
    # Знаходимо ПЛАН і ФАКТ саме за цю дату
    df_plan_comp = df_all[df_all['Time'].dt.date == last_f_date]
    df_fact_comp = df_fact[df_fact['Time'].dt.date == last_f_date]
    
    if not df_plan_comp.empty and not df_fact_comp.empty:
        c1, c2 = st.columns([2, 1])
        with c1:
            fig2 = go.Figure()
            # План, який давала модель (пунктир)
            fig2.add_trace(go.Scatter(x=df_plan_comp['Time'], y=df_plan_comp['Power_MW'], name="Очікувано (Модель)", line=dict(color='rgba(241, 196, 15, 0.4)', dash='dot')))
            # Реальний факт з пошти (суцільна лінія)
            fig2.add_trace(go.Scatter(x=df_fact_comp['Time'], y=df_fact_comp['Fact_MW'], name="Отримано (АСКОЕ)", line=dict(color='#e74c3c', width=3)))
            fig2.update_layout(template="plotly_dark", title=f"Точність прогнозу за {last_f_date.strftime('%d.%m')}", height=400)
            st.plotly_chart(fig2, use_container_width=True)
            
        with c2:
            st.markdown("<div class='ai-card'>", unsafe_allow_html=True)
            st.subheader("🤖 Вердикт ШІ")
            p_s = df_plan_comp['Power_MW'].sum()
            f_s = df_fact_comp['Fact_MW'].sum()
            if p_s > 0:
                acc = (1 - abs(p_s - f_s)/p_s) * 100
                st.write(f"**Точність моделі:** {acc:.1f}%")
                st.write(f"**Відхилення:** {f_s - p_s:.2f} MWh")
                st.markdown("---")
                if acc >= 90: st.success("✅ Корекція не потрібна. Модель v2.6 стабільна.")
                else: st.warning("⚠️ Потрібна корекція коефіцієнтів.")
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info(f"Чекаємо синхронізації нового звіту АСКОЕ. Остання доступна аналітика за: {last_f_date}")
