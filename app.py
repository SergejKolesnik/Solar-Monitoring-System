import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time

# 1. Налаштування
st.set_page_config(page_title="Solar AI Nikopol", layout="wide", initial_sidebar_state="collapsed")

# 2. Отримання ВСІХ даних (7 днів минулого + 3 майбутнього)
@st.cache_data(ttl=300)
def get_combined_data():
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
        # Наша модель v2.6 (11.4 MW)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00092 * (1 - df['Clouds']/100 * 0.4)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

# 3. Завантаження ФАКТУ з GitHub
def get_fact_data():
    try:
        v_tag = int(time.time() / 60)
        repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
        df = pd.read_csv(repo_url)
        df['Time'] = pd.to_datetime(df['Time'])
        return df
    except: return None

# --- ВИКОНАННЯ ---
df_all = get_combined_data()
df_fact = get_fact_data()

st.title("☀️ Solar AI Monitor: Оперативне управління")

if df_all is not None:
    now = datetime.now()
    today_date = now.date()
    
    # ВЕРХНІЙ БЛОК: ПРОГНОЗ
    df_today = df_all[df_all['Time'].dt.date == today_date]
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("Прогноз на сьогодні", f"{df_today['Power_MW'].sum():.1f} MWh")
    with m2: st.metric("Температура Нікополь", f"{df_today.iloc[now.hour]['Temp'] if not df_today.empty else 0}°C")
    with m3: st.metric("Статус СЕС", "11.4 MW Online")

    df_future = df_all[df_all['Time'] >= pd.Timestamp(today_date)]
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=df_future['Time'], y=df_future['Power_MW'], name="План (MW)", fill='tozeroy', line=dict(color='#f1c40f', width=4)))
    fig1.update_layout(template="plotly_dark", title="План генерації (сьогодні + 2 дні)", height=400, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig1, use_container_width=True)

    st.markdown("---")

    # НИЖНІЙ БЛОК: АНАЛІТИКА (Шукаємо останню дату факту)
    if df_fact is not None:
        st.header("📉 Ретроспективний аналіз та корекція ШІ")
        last_f_date = df_fact['Time'].dt.date.max()
        
        # Порівнюємо саме цю дату
        df_p_comp = df_all[df_all['Time'].dt.date == last_f_date]
        df_f_comp = df_fact[df_fact['Time'].dt.date == last_f_date]
        
        if not df_p_comp.empty and not df_f_comp.empty:
            c1, c2 = st.columns([2, 1])
            with c1:
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(x=df_p_comp['Time'], y=df_p_comp['Power_MW'], name="План (Модель)", line=dict(color='rgba(241, 196, 15, 0.4)', dash='dot')))
                fig2.add_trace(go.Scatter(x=df_f_comp['Time'], y=df_f_comp['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#e74c3c', width=3)))
                fig2.update_layout(template="plotly_dark", title=f"Аналіз точності за {last_f_date.strftime('%d.%m')}", height=400)
                st.plotly_chart(fig2, use_container_width=True)
            with c2:
                st.subheader("🤖 Вердикт ШІ")
                p_s, f_s = df_p_comp['Power_MW'].sum(), df_f_comp['Fact_MW'].sum()
                acc = (1 - abs(p_s - f_s)/p_s)*100 if p_s > 0 else 0
                st.write(f"**Точність:** {acc:.1f}%")
                if acc >= 90: st.success("✅ Модель стабільна")
                else: st.warning("⚠️ Потрібна корекція")
        else:
            st.info(f"Очікуємо звіт АСКОЕ. Останній факт у системі: {last_f_date}")
