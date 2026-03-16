import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import time
import pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v4.8", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. ФУНКЦІЯ ПОГОДИ
@st.cache_data(ttl=3600)
def get_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        # Запитуємо дані від -3 дні до +7 днів
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

# 3. ПІДГОТОВКА ДАНИХ
df_all = get_weather_data()
if isinstance(df_all, str): st.error(df_all); st.stop()

# Готуємо змінні для обох вкладок
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
current_data = df_today[df_today['Time'].dt.hour == now_ua.hour].iloc[0] if not df_today.empty else df_all.iloc[0]

ai_bias = 1.0
df_fact = None
try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
    
    # НАВЧАННЯ ШІ: Порівнюємо історію
    hist_times = df_fact['Time'].unique()
    base_hist = df_all[df_all['Time'].isin(hist_times)]['Radiation'].sum()
    fact_hist = df_fact['Fact_MW'].sum()
    # 11.4 - потужність, 0.001 - коефіцієнт переводу радіації в МВт
    if base_hist > 0:
        theoretical_sum = base_hist * 11.4 * 0.001 
        ai_bias = fact_hist / theoretical_sum
except: pass

df_all['Power_MW'] = df_all['Radiation'] * 11.4 * 0.001 * ai_bias

# 4. ІНТЕРФЕЙС
st.title("🚀 SkyGrid: Solar AI Nikopol")

tab1, tab2 = st.tabs(["📊 МОНІТОРИНГ ТА НАВЧАННЯ", "🌦 ПРОГНОЗ ПОГОДИ"])

with tab1:
    col1, col2, col3 = st.columns(3)
    col1.metric("ШІ ПЛАН (СЬОГОДНІ)", f"{df_today['Radiation'].sum() * 11.4 * 0.001 * ai_bias:.1f} MWh", f"{ai_bias:.2f}x bias")
    col2.metric("ТЕМПЕРАТУРА", f"{current_data['Temp']:.1f}°C")
    col3.metric("СТАТУС СЕС", "11.4 MW Online")

    # Графік прогнозу (Зелений)
    fig_p = go.Figure()
    df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(24)
    fig_p.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="План", fill='tozeroy', line=dict(color='#00ff7f')))
    fig_p.update_layout(height=300, title="Оперативний план на 24г", template="plotly_dark")
    st.plotly_chart(fig_p, use_container_width=True)

    # ЗОНА ПОРІВНЯННЯ (Ось тут навчання!)
    if df_fact is not None:
        st.subheader("🧠 Порівняння Факт vs План (Навчання ШІ)")
        df_comp = pd.merge(df_fact, df_all[['Time', 'Radiation']], on='Time', how='left')
        df_comp['AI_Plan'] = df_comp['Radiation'] * 11.4 * 0.001 * ai_bias
        
        fig_c = go.Figure()
        fig_c.add_trace(go.Scatter(x=df_comp['Time'], y=df_comp['Fact_MW'], name="ФАКТ (АСКОЕ)", line=dict(color='#ff4b4b', width=3)))
        fig_c.add_trace(go.Scatter(x=df_comp['Time'], y=df_comp['AI_Plan'], name="ПЛАН ШІ", line=dict(color='white', width=2, dash='dot')))
        fig_c.update_layout(height=350, template="plotly_dark")
        st.plotly_chart(fig_c, use_container_width=True)

with tab2:
    # Твій улюблений візуальний прогноз
    f_date = df_today['Time'].dt.date.iloc[0].strftime("%d.%m.%Y") if not df_today.empty else "---"
    st.markdown(f"<h2 style='text-align: center;'>📅 Прогноз на сьогодні: {f_date}</h2>", unsafe_allow_html=True)
    
    c1, c2 = st.columns([1, 2])
    with c1:
        st.markdown(f"""
            <div style='background: rgba(255,255,255,0.05); padding: 20px; border-radius: 15px; text-align: center; border: 1px solid #32383e;'>
                <p style='font-size: 80px; margin: 0;'>{get_weather_icon(current_data['Clouds'], current_data['Rain'])}</p>
                <p style='font-size: 42px; font-weight: bold; margin: 0;'>{current_data['Temp']:.0f}°C</p>
                <p style='color: #FFD700;'>{current_data['Radiation']:.0f} W/m²</p>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        chart_data = df_today.set_index('Time')[['Radiation']]
        st.area_chart(chart_data, color="#FFD700", height=250)
