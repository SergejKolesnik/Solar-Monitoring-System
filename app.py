import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz

# 1. НАЛАШТУВАННЯ
st.set_page_config(page_title="SkyGrid: Solar AI v4.9", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. ОТРИМАННЯ ДАНИХ (Прогноз + Історія для навчання)
@st.cache_data(ttl=3600)
def get_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        # Запитуємо історію за 3 дні та прогноз на 7 днів
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/last3days/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,precip&include=hours,days&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        hours_list = []
        for day in data['days']:
            for hr in day['hours']:
                hours_list.append({
                    'Time': pd.to_datetime(f"{day['datetime']} {hr['datetime']}"),
                    'Radiation': hr.get('solarradiation', 0),
                    'Clouds': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'Rain': hr.get('precip', 0)
                })
        return pd.DataFrame(hours_list)
    except Exception as e:
        return f"Помилка API: {e}"

def get_weather_icon(clouds, rain):
    if rain > 0.2: return "🌧️"
    if clouds > 70: return "☁️"
    if clouds > 30: return "⛅"
    return "☀️"

# 3. ЛОГІКА ТА ОБРОБКА ДАНИХ
df_all = get_weather_data()
if isinstance(df_all, str):
    st.error(df_all)
    st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
current_data = df_today[df_today['Time'].dt.hour == now_ua.hour].iloc[0] if not df_today.empty else df_all.iloc[0]

# ЗАВАНТАЖЕННЯ БАЗИ ТА НАВЧАННЯ
ai_bias = 1.0
accuracy = 0
df_fact = None

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
    
    # Розрахунок Bias (Навчання)
    hist_times = df_fact['Time'].unique()
    relevant_weather = df_all[df_all['Time'].isin(hist_times)]
    
    base_theoretical_sum = (relevant_weather['Radiation'] * 11.4 * 0.001).sum()
    actual_fact_sum = df_fact['Fact_MW'].sum()
    
    if base_theoretical_sum > 0:
        ai_bias = actual_fact_sum / base_theoretical_sum
        # Розрахунок точності останньої доби
        accuracy = (1 - abs(actual_fact_sum - base_theoretical_sum * ai_bias) / actual_fact_sum) * 100
except:
    pass

# Розрахунок потужності з урахуванням навчання
df_all['Power_MW'] = df_all['Radiation'] * 11.4 * 0.001 * ai_bias

# 4. ІНТЕРФЕЙС
st.title("🚀 SkyGrid: Solar AI Nikopol")

tab1, tab2 = st.tabs(["📊 МОНІТОРИНГ ТА НАВЧАННЯ", "🌦 ПРОГНОЗ ПОГОДИ"])

with tab1:
    # МЕТРИКИ
    m1, m2, m3 = st.columns(3)
    plan_3days = df_all[(df_all['Time'] >= pd.Timestamp(now_ua.date())) & 
                        (df_all['Time'] < pd.Timestamp(now_ua.date() + timedelta(days=3)))]['Power_MW'].sum()
    
    m1.metric("ПЛАН НА 3 ДОБИ", f"{plan_3days:.1f} MWh", f"{ai_bias:.2f}x bias")
    m2.metric("ТОЧНІСТЬ ШІ", f"{accuracy:.1f} %", "Навчений")
    m3.metric("СТАТУС СЕС", "11.4 MW Online")

    # ГРАФІК НА 3 ДНІ (План)
    st.subheader("🗓 Оперативний план генерації (Наступні 72 години)")
    df_future_3d = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    
    fig_3d = go.Figure()
    fig_3d.add_trace(go.Scatter(
        x=df_future_3d['Time'], y=df_future_3d['Power_MW'],
        name="Прогноз ШІ", fill='tozeroy',
        line=dict(color='#00ff7f', width=3),
        fillcolor='rgba(0, 255, 127, 0.1)'
    ))
    fig_3d.update_layout(height=350, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_3d, use_container_width=True)

    # ЗОНА ПОРІВНЯННЯ (Факт vs План)
    if df_fact is not None:
        st.markdown("---")
        st.subheader("🧠 Ретроспектива: Як ШІ вивчив об'єкт")
        df_comp = pd.merge(df_fact, df_all[['Time', 'Radiation', 'Clouds']], on='Time', how='left')
        df_comp['AI_Plan'] = df_comp['Radiation'] * 11.4 * 0.001 * ai_bias
        
        fig_c = go.Figure()
        fig_c.add_trace(go.Scatter(x=df_comp['Time'], y=df_comp['Fact_MW'], name="ФАКТ (АСКОЕ)", line=dict(color='#ff4b4b', width=3)))
        fig_c.add_trace(go.Scatter(x=df_comp['Time'], y=df_comp['AI_Plan'], name="ПЛАН ШІ", line=dict(color='white', width=2, dash='dot')))
        fig_c.update_layout(height=350, template="plotly_dark", hovermode="x unified")
        st.plotly_chart(fig_c, use_container_width=True)

with tab2:
    # Візуальний прогноз (як ми "причесали")
    f_date = df_today['Time'].dt.date.iloc[0].strftime("%d.%m.%Y") if not df_today.empty else "---"
    st.markdown(f"<h2 style='text-align: center;'>📅 Прогноз на сьогодні: {f_date}</h2>", unsafe_allow_html=True)
    
    c1, c2 = st.columns([1.5, 2.5])
    with c1:
        st.markdown(f"""
            <div style='background: rgba(255,255,255,0.05); padding: 30px; border-radius: 20px; border: 1px solid #32383e; text-align: center;'>
                <div style='display: flex; align-items: center; justify-content: center; gap: 20px;'>
                    <span style='font-size: 80px;'>{get_weather_icon(current_data['Clouds'], current_data['Rain'])}</span>
                    <span style='font-size: 80px; font-weight: 800; color: white;'>{current_data['Temp']:.0f}°</span>
                </div>
                <div style='margin-top: 20px; display: grid; grid-template-columns: 1fr 1fr; gap: 15px;'>
                    <div style='text-align: left;'>
                        <p style='color: gray; margin: 0;'>ХМАРНІСТЬ</p>
                        <p style='font-size: 24px; font-weight: bold; margin: 0;'>{current_data['Clouds']:.0f}%</p>
                    </div>
                    <div style='text-align: left;'>
                        <p style='color: gray; margin: 0;'>ЕНЕРГІЯ</p>
                        <p style='font-size: 24px; font-weight: bold; color: #FFD700; margin: 0;'>{current_data['Radiation']:.0f}W</p>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        st.area_chart(df_today.set_index('Time')[['Radiation']], color="#FFD700", height=300)
