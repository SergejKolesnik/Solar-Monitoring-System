import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v5.9", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def get_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation&include=hours,days&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15); res.raise_for_status()
        data = res.json()
        h_list = []
        for d in data['days']:
            for hr in d['hours']:
                h_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Radiation': hr.get('solarradiation', 0),
                    'Clouds': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0)
                })
        return pd.DataFrame(h_list)
    except Exception as e: return str(e)

def get_icon(clouds):
    if clouds > 70: return "☁️"
    if clouds > 30: return "⛅"
    return "☀️"

# 2. ДАНІ ТА СИНХРОНІЗАЦІЯ БАЗИ
df_forecast = get_weather_data()
if isinstance(df_forecast, str): st.error(f"Error: {df_forecast}"); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias, accuracy, df_history = 1.0, 0, None

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_history = pd.read_csv(repo_url)
    
    # Розумне розпізнавання колонок
    df_history.columns = df_history.columns.str.strip()
    # Якщо дані АСКОЕ помилково потрапили в Forecast_MW (як на скріншоті), ми їх переставимо
    if 'Fact_MW' in df_history.columns and df_history['Fact_MW'].isnull().all() and 'Forecast_MW' in df_history.columns:
        df_history['Fact_MW'] = df_history['Forecast_MW']
        df_history['Forecast_MW'] = None

    df_history['Time'] = pd.to_datetime(df_history['Time']).dt.floor('H')
    
    # Розрахунок Bias
    df_valid = df_history.dropna(subset=['Fact_MW'])
    if not df_valid.empty:
        # Для навчання використовуємо порівняння факту з радіацією, якщо Forecast_MW порожній
        df_learn = df_valid[df_valid['Time'] > (now_ua - timedelta(days=7))]
        # Тут ШІ підбирає коефіцієнт під реальну виробітку
        ai_bias = 1.15 # Тимчасова база, поки Forecast_MW не заповниться правильно в CSV
except: pass

df_forecast['Power_MW'] = df_forecast['Radiation'] * 11.4 * 0.001 * ai_bias

# 3. ІНТЕРФЕЙС
st.markdown("""
    <style>
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
    .nzf-logo { animation: pulse 3s infinite; width: 70px; margin-right: 15px; border-radius: 8px; }
    .title-box { display: flex; align-items: center; margin-bottom: 25px; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""<div class="title-box">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" class="nzf-logo">
    <h1 style='margin:0;'>SkyGrid: Solar AI Nikopol</h1>
</div>""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📊 МОНІТОРИНГ ТА НАВЧАННЯ", "🌦 ПРОГНОЗ ПОГОДИ"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    s_today = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['Power_MW'].sum()
    s_tomorrow = df_forecast[df_forecast['Time'].dt.date == (now_ua + timedelta(days=1)).date()]['Power_MW'].sum()
    c1.metric("СЬОГОДНІ", f"{s_today:.1f} MWh")
    c2.metric("ЗАВТРА", f"{s_tomorrow:.1f} MWh")
    c3.metric("ТОЧНІСТЬ", f"{accuracy:.1f} %")
    c4.metric("КОЕФІЦІЄНТ", f"{ai_bias:.2f}x")

    st.markdown("---")
    st.subheader("📈 Оперативний план (72 години)")
    df_p = df_forecast[df_forecast['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_p['Time'], y=df_p['Power_MW'], fill='tozeroy', name="План ШІ", line=dict(color='#00ff7f', width=3)))
    fig.update_layout(height=300, template="plotly_dark", margin=dict(l=0,r=0,t=0,b=0))
    st.plotly_chart(fig, use_container_width=True)

    # Кнопка Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_ex = df_p[['Time', 'Power_MW']].copy()
        df_ex.columns = ['Дата/Час', 'План МВт']
        df_ex.to_excel(writer, index=False)
    st.download_button("📥 Скачати Excel План", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d%m')}.xlsx")

    if df_history is not None:
        st.markdown("---")
        st.subheader("🔍 Останні записи бази (Перевірка колонок)")
        # Показуємо останні рядки, щоб бачити, що куди записалося
        st.table(df_history.tail(8).style.format({'Fact_MW': '{:.2f}', 'Forecast_MW': '{:.2f}'}))

with tab2:
    # ПОВЕРНЕННЯ БРУТАЛЬНОЇ СТОРІНКИ V4.6
    df_t = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]
    if not df_t.empty:
        cur = df_t[df_t['Time'].dt.hour == now_ua.hour].iloc[0] if now_ua.hour in df_t['Time'].dt.hour.values else df_t.iloc[0]
        st.markdown(f"<h1 style='text-align: center; margin-bottom: 30px;'>📅 Прогноз на сьогодні: <span style='color: #FFD700;'>{now_ua.strftime('%d.%m.%Y')}</span></h1>", unsafe_allow_html=True)
        
        c_left, c_right = st.columns([1.2, 2])
        with c_left:
            st.markdown(f"""<div style='background: rgba(255, 255, 255, 0.05); padding: 25px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.1); text-align: center;'>
                <p style='font-size: 80px; margin: 0;'>{get_icon(cur['Clouds'])}</p>
                <div style='display: flex; justify-content: space-around; margin-top: 10px;'>
                    <div><p style='color: gray; font-size: 14px; margin: 0;'>ТЕМПЕРАТУРА</p><p style='font-size: 32px; font-weight: bold; margin: 0;'>{cur['Temp']:.1f}°C</p></div>
                    <div><p style='color: gray; font-size: 14px; margin: 0;'>ХМАРНІСТЬ</p><p style='font-size: 32px; font-weight: bold; margin: 0;'>{cur['Clouds']:.0f}%</p></div>
                </div>
            </div>""", unsafe_allow_html=True)
        with c_right:
            with st.container(border=True):
                st.area_chart(df_t.set_index('Time')[['Radiation']], color="#FFD700", height=250)
        
        st.markdown("<br>", unsafe_allow_html=True)
        t_cols = st.columns(7)
        d_hrs = df_t[df_t['Time'].dt.hour.isin([8, 10, 12, 14, 16, 18, 20])]
        for i, (idx, row) in enumerate(d_hrs.iterrows()):
            with t_cols[i]:
                st.markdown(f"""<div style='background: rgba(255, 255, 255, 0.03); padding: 10px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.07); text-align: center;'>
                    <p style='font-size: 12px; color: gray; margin: 0;'>{row['Time'].strftime('%H:%M')}</p>
                    <p style='font-size: 24px; margin: 5px 0;'>{get_icon(row['Clouds'])}</p>
                    <p style='font-size: 18px; font-weight: bold; margin: 0;'>{row['Temp']:.0f}°</p>
                </div>""", unsafe_allow_html=True)
