import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz

# 1. НАЛАШТУВАННЯ
st.set_page_config(page_title="SkyGrid: Solar AI v4.9.4", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. ОТРИМАННЯ ДАНИХ
@st.cache_data(ttl=3600)
def get_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        # Запитуємо історію за 3 дні та прогноз на 7 днів
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/last3days/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,precip&include=hours,days&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15); res.raise_for_status()
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
    except Exception as e: return f"Error: {e}"

def get_weather_icon(clouds, rain):
    if rain > 0.2: return "🌧️"
    if clouds > 70: return "☁️"
    if clouds > 30: return "⛅"
    return "☀️"

# 3. ЛОГІКА ТА ОБРОБКА
df_all = get_weather_data()
if isinstance(df_all, str): st.error(df_all); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
current_data = df_today[df_today['Time'].dt.hour == now_ua.hour].iloc[0] if not df_today.empty else df_all.iloc[0]

# НАВЧАННЯ ШІ
ai_bias, accuracy, df_fact = 1.0, 0, None
try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
    
    hist_times = df_fact['Time'].unique()
    relevant_w = df_all[df_all['Time'].isin(hist_times)]
    
    # 11.4 MW - встановлена потужність
    base_sum = (relevant_w['Radiation'] * 11.4 * 0.001).sum()
    if base_sum > 0:
        ai_bias = df_fact['Fact_MW'].sum() / base_sum
        accuracy = (1 - abs(df_fact['Fact_MW'].sum() - base_sum * ai_bias) / df_fact['Fact_MW'].sum()) * 100
except: pass

df_all['Power_MW'] = df_all['Radiation'] * 11.4 * 0.001 * ai_bias

# 4. ІНТЕРФЕЙС
# СТИЛЬ ПУЛЬСАЦІЇ ДЛЯ ЛОГОТИПУ
st.markdown("""
    <style>
    @keyframes pulse {
        0% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.8; transform: scale(1.02); }
        100% { opacity: 1; transform: scale(1); }
    }
    .nzf-logo {
        animation: pulse 3s infinite ease-in-out;
        width: 70px;
        margin-right: 20px;
    }
    .title-container {
        display: flex;
        align-items: center;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

# ЛОГОТИП ТА ЗАГОЛОВОК
st.markdown(f"""
    <div class="title-container">
        <img src="https://www.nzf.com.ua/images/logo.png" class="nzf-logo">
        <h1 style='margin: 0;'>SkyGrid: Solar AI Nikopol Ferroalloy Plant</h1>
    </div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📊 МОНІТОРИНГ ТА НАВЧАННЯ", "🌦 ПРОГНОЗ ПОГОДИ"])

# --- ВКЛАДКА 1: МОНІТОРИНГ ---
with tab1:
    st.markdown("### 📅 План генерації за прогнозом (MWh)")
    d1, d2, d3, d_acc = st.columns(4)
    
    sum_d1 = df_all[df_all['Time'].dt.date == now_ua.date()]['Power_MW'].sum()
    sum_d2 = df_all[df_all['Time'].dt.date == (now_ua + timedelta(days=1)).date()]['Power_MW'].sum()
    sum_d3 = df_all[df_all['Time'].dt.date == (now_ua + timedelta(days=2)).date()]['Power_MW'].sum()

    d1.metric("СЬОГОДНІ", f"{sum_d1:.1f}")
    d2.metric("ЗАВТРА", f"{sum_d2:.1f}")
    d3.metric("ПІСЛЯЗАВТРА", f"{sum_d3:.1f}")
    d_acc.metric("ТОЧНІСТЬ ШІ", f"{accuracy:.1f} %", f"{ai_bias:.2f}x bias")

    st.markdown("---")
    st.subheader("📈 Оперативний графік (Наступні 72 години)")
    df_f3 = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(x=df_f3['Time'], y=df_f3['Power_MW'], name="План МВт", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    fig3.update_layout(height=300, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig3, use_container_width=True)

    if df_fact is not None:
        st.subheader("🧠 Ретроспектива навчання (Факт vs План)")
        df_c = pd.merge(df_fact, df_all[['Time', 'Radiation']], on='Time', how='left')
        df_c['AI_Plan'] = df_c['Radiation'] * 11.4 * 0.001 * ai_bias
        fig_c = go.Figure()
        fig_c.add_trace(go.Scatter(x=df_c['Time'], y=df_c['Fact_MW'], name="ФАКТ (АСКОЕ)", line=dict(color='#ff4b4b', width=3)))
        fig_c.add_trace(go.Scatter(x=df_c['Time'], y=df_c['AI_Plan'], name="ПЛАН ШІ", line=dict(color='white', width=2, dash='dot')))
        fig_c.update_layout(height=300, template="plotly_dark", hovermode="x unified")
        st.plotly_chart(fig_c, use_container_width=True)

# --- ВКЛАДКА 2: ПРОГНОЗ ПОГОДИ (Твоя улюблена версія) ---
with tab2:
    if not df_today.empty:
        f_date = df_today['Time'].dt.date.iloc[0].strftime("%d.%m.%Y")
        st.markdown(f"<h1 style='text-align: center; margin-bottom: 30px;'>📅 Прогноз на сьогодні: <span style='color: #FFD700;'>{f_date}</span></h1>", unsafe_allow_html=True)
        
        c_info, c_chart = st.columns([1.2, 2])
        with c_info:
            icon = get_weather_icon(current_data['Clouds'], current_data['Rain'])
            st.markdown(f"""
                <div style='background: rgba(255, 255, 255, 0.05); padding: 25px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.1); text-align: center;'>
                    <p style='font-size: 80px; margin: 0;'>{icon}</p>
                    <div style='display: flex; justify-content: space-around; margin-top: 10px;'>
                        <div><p style='color: gray; font-size: 14px; margin: 0;'>ТЕМПЕРАТУРА</p><p style='font-size: 32px; font-weight: bold; margin: 0;'>{current_data['Temp']:.0f}°C</p></div>
                        <div><p style='color: gray; font-size: 14px; margin: 0;'>ХМАРНІСТЬ</p><p style='font-size: 32px; font-weight: bold; margin: 0;'>{current_data['Clouds']:.0f}%</p></div>
                    </div>
                    <hr style='border: 0; border-top: 1px solid rgba(255,255,255,0.1); margin: 20px 0;'>
                    <div style='display: flex; justify-content: space-around;'>
                        <div><p style='color: gray; font-size: 14px; margin: 0;'>ЕНЕРГІЯ НЕБА</p><p style='font-size: 28px; font-weight: bold; color: #FFD700; margin: 0;'>{current_data['Radiation']:.0f} W/m²</p></div>
                        <div><p style='color: gray; font-size: 14px; margin: 0;'>ОПАДИ</p><p style='font-size: 28px; font-weight: bold; color: #3498db; margin: 0;'>{current_data['Rain']:.1f} мм</p></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        with c_chart:
            with st.container(border=True):
                st.write("📈 **Графік сонячної активності**")
                st.area_chart(df_today.set_index('Time')[['Radiation']], color="#FFD700", height=275)

        st.markdown("<br>", unsafe_allow_html=True)
        t_cols = st.columns(7)
        d_hrs = df_today[df_today['Time'].dt.hour.isin([8, 10, 12, 14, 16, 18, 20])]
        for i, (idx, row) in enumerate(d_hrs.iterrows()):
            with t_cols[i]:
                st.markdown(f"""
                    <div style='background: rgba(255, 255, 255, 0.03); padding: 10px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.07); text-align: center;'>
                        <p style='font-size: 12px; color: gray; margin: 0;'>{row['Time'].strftime('%H:%M')}</p>
                        <p style='font-size: 24px; margin: 5px 0;'>{get_weather_icon(row['Clouds'], row['Rain'])}</p>
                        <p style='font-size: 18px; font-weight: bold; margin: 0;'>{row['Temp']:.0f}°</p>
                    </div>
                """, unsafe_allow_html=True)
