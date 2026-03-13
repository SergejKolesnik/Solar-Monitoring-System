import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Solar AI Nikopol", layout="wide")

# Стилізація
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; margin-bottom: 25px; }
    h2 { color: #ffffff; font-weight: 300; border-left: 5px solid #f1c40f; padding-left: 15px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=600)
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m&timezone=auto&forecast_days=3"
    try:
        data = requests.get(url).json()
        h = data['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m']
        })
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00092 * (1 - df['Clouds']/100 * 0.4)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

df_forecast = get_weather_data()

# --- ЗАВАНТАЖЕННЯ ФАКТУ ---
df_fact = None
try:
    v_tag = int(time.time())
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
except: pass

# --- ЕКРАН 1: ОПЕРАТИВНИЙ ПРОГНОЗ ---
st.title("☀️ Solar AI Monitor: Оперативне управління")
m1, m2, m3 = st.columns(3)
with m1: st.metric("Прогноз на сьогодні", f"{df_forecast[df_forecast['Time'].dt.date == datetime.now().date()]['Power_MW'].sum():.1f} MWh")
with m2: st.metric("Температура", f"{df_forecast.iloc[datetime.now().hour]['Temp']}°C")
with m3: st.metric("Статус СЕС", "11.4 MW Online")

fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df_forecast['Time'], y=df_forecast['Power_MW'], name="Прогноз (MW)", fill='tozeroy', line=dict(color='#f1c40f', width=4)))
fig1.update_layout(template="plotly_dark", title="Майбутня генерація (3 дні)", height=400, margin=dict(l=10, r=10, t=40, b=10))
st.plotly_chart(fig1, use_container_width=True)

st.markdown("---")

# --- ЕКРАН 2: АНАЛІТИКА ТА КОРЕКЦІЯ ШІ ---
if df_fact is not None:
    st.header("📉 Аналіз точності та корекція моделі")
    
    # Створюємо порівняльну таблицю за датами факту
    fact_dates = df_fact['Time'].dt.date.unique()
    # Беремо прогноз за ці ж дати (нам треба завантажити минулу погоду для точного порівняння, 
    # але поки використовуємо останній збережений прогноз)
    
    col_a, col_b = st.columns([3, 1])
    
    with col_a:
        fig2 = go.Figure()
        # Відображаємо факт
        fig2.add_trace(go.Scatter(x=df_fact['Time'], y=df_fact['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#e74c3c', width=3)))
        # Для порівняння додамо лінію моделі (тут ШІ в майбутньому буде малювати свою "корекцію")
        fig2.update_layout(template="plotly_dark", title="Ретроспективний аналіз (Минулі звіти)", height=400)
        st.plotly_chart(fig2, use_container_width=True)
        
    with col_b:
        st.subheader("Показники ШІ")
        total_fact = df_fact['Fact_MW'].sum()
        st.write(f"**Завантажено за:** {fact_dates[-1]}")
        st.write(f"**Виробіток:** {total_fact:.2f} MWh")
        
        # Симуляція корекції ШІ
        error = 4.2 # Наприклад
        st.warning(f"Відхилення моделі: {error}%")
        st.info("ШІ рекомендує: Коефіцієнт хмарності змінити з 0.4 на 0.42")

else:
    st.info("Дані для аналітики ШІ з'являться після завантаження першого звіту АСКОЕ.")
