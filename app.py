import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Solar AI Nikopol", layout="wide", initial_sidebar_state="collapsed")

# Дизайн
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .ai-card { background: rgba(241, 196, 15, 0.05); border: 1px solid #f1c40f; border-radius: 10px; padding: 20px; margin-top: 20px; }
    </style>
    """, unsafe_allow_html=True)

# Оновлена функція з обходом кешу
def get_weather_data():
    # Запитуємо вчорашній день (past_days=1)
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m&timezone=auto&past_days=1&forecast_days=3"
    try:
        res = requests.get(url)
        data = res.json()
        h = data['hourly']
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
    except Exception as e:
        st.error(f"Помилка API: {e}")
        return None

# --- ЗАВАНТАЖЕННЯ ---
df_forecast = get_weather_data()
df_fact = None

try:
    v_tag = int(time.time() / 60) # Оновлення раз на хвилину
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
except:
    pass

# --- БЛОК 1: ОПЕРАТИВНИЙ МОНІТОРИНГ ---
st.title("☀️ Solar AI Monitor: Оперативне управління")

if df_forecast is not None:
    today_date = datetime.now().date()
    # Метрики на основі сьогоднішніх даних
    df_today = df_forecast[df_forecast['Time'].dt.date == today_date]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Прогноз на сьогодні", f"{df_today['Power_MW'].sum():.1f} MWh")
    with col2:
        curr_hour = datetime.now().hour
        temp_val = df_today.iloc[curr_hour]['Temp'] if not df_today.empty else 0
        st.metric("Температура Нікополь", f"{temp_val}°C")
    with col3:
        st.metric("Статус СЕС", "11.4 MW Online")

    # Головний графік (тільки майбутнє)
    fig1 = go.Figure()
    df_future = df_forecast[df_forecast['Time'] >= pd.Timestamp(today_date)]
    fig1.add_trace(go.Scatter(x=df_future['Time'], y=df_future['Power_MW'], name="Прогноз (MW)", fill='tozeroy', line=dict(color='#f1c40f', width=4)))
    fig1.update_layout(template="plotly_dark", title="План генерації (сьогодні + 2 дні)", height=400)
    st.plotly_chart(fig1, use_container_width=True)

st.markdown("---")

# --- БЛОК 2: АНАЛІТИКА ШІ (ПОРІВНЯННЯ ЗА ВЧОРА) ---
if df_fact is not None and df_forecast is not None:
    st.header("📉 Ретроспективний аналіз та корекція ШІ")
    
    # Беремо останню дату з файлу АСКОЕ (12.03)
    last_fact_date = df_fact['Time'].dt.date.max()
    
    # Фільтруємо обидва датасети за цю дату
    df_plan_comp = df_forecast[df_forecast['Time'].dt.date == last_fact_date]
    df_fact_comp = df_fact[df_fact['Time'].dt.date == last_fact_date]
    
    if not df_plan_comp.empty and not df_fact_comp.empty:
        c_graph, c_ai = st.columns([2, 1])
        with c_graph:
            fig2 = go.Figure()
            # План (Пунктир)
            fig2.add_trace(go.Scatter(x=df_plan_comp['Time'], y=df_plan_comp['Power_MW'], name="План (Модель)", line=dict(color='rgba(241, 196, 15, 0.5)', dash='dot')))
            # Факт (Червона лінія)
            fig2.add_trace(go.Scatter(x=df_fact_comp['Time'], y=df_fact_comp['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#e74c3c', width=3)))
            fig2.update_layout(template="plotly_dark", title=f"Порівняння за {last_fact_date}", height=400)
            st.plotly_chart(fig2, use_container_width=True)
            
        with c_ai:
            st.markdown("<div class='ai-card'>", unsafe_allow_html=True)
            st.subheader("🤖 Вердикт ШІ")
            p_sum = df_plan_comp['Power_MW'].sum()
            f_sum = df_fact_comp['Fact_MW'].sum()
            if p_sum > 0:
                acc = (1 - abs(p_sum - f_sum)/p_sum) * 100
                st.write(f"**Точність моделі:** {acc:.1f}%")
                st.write(f"**Відхилення:** {f_sum - p_sum:.2f} MWh")
                st.markdown("---")
                if acc >= 90: st.success("✅ Модель v2.6 підтверджена.")
                else: st.warning("⚠️ Потрібна корекція!")
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info(f"Дані за {last_fact_date} ще не підвантажені в модель погоди. Спробуйте оновити сторінку.")
else:
    st.info("Очікуємо звіт АСКОЕ.")
