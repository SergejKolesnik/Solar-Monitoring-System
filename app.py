import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v6.5", layout="wide")
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

# 2. АНАЛІТИКА ШІ
df_forecast = get_weather_data()
if isinstance(df_forecast, str): st.error(f"Error: {df_forecast}"); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias, accuracy, df_history = 1.0, 0, None

try:
    # Завантаження бази з GitHub з анти-кешем
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_history = pd.read_csv(repo_url)
    df_history['Time'] = pd.to_datetime(df_history['Time'])
    
    # 🧠 ЛОГІКА ПОРІВНЯННЯ
    # Беремо рядки, де заповнені ОБИДВІ колонки (Факт і Прогноз)
    df_compare = df_history.dropna(subset=['Fact_MW', 'Forecast_MW'])
    
    # Виключаємо нульові години (ніч), щоб не псувати статистику
    df_compare = df_compare[df_compare['Forecast_MW'] > 0.1]
    
    if not df_compare.empty:
        # Навчаємось на останніх 7 днях
        df_recent = df_compare[df_compare['Time'] > (now_ua - timedelta(days=7))]
        
        sum_fact = df_recent['Fact_MW'].sum()
        sum_forecast = df_recent['Forecast_MW'].sum()
        
        if sum_forecast > 0:
            # Розрахунок коефіцієнта (Bias)
            ai_bias = sum_fact / sum_forecast
            # Розрахунок точності (MAPE інверсія)
            error = abs(sum_fact - sum_forecast) / sum_fact if sum_fact > 0 else 0
            accuracy = max(0, min(100, (1 - error) * 100))
except Exception as e:
    st.sidebar.warning(f"AI Syncing... {e}")

# Корекція майбутнього прогнозу
df_forecast['Power_MW'] = df_forecast['Radiation'] * 11.4 * 0.001 * ai_bias

# 3. ІНТЕРФЕЙС
st.markdown("""
    <style>
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.7; } 100% { opacity: 1; } }
    .nzf-logo { animation: pulse 3s infinite; width: 65px; margin-right: 15px; border-radius: 8px; }
    .title-box { display: flex; align-items: center; margin-bottom: 25px; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""<div class="title-box">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" class="nzf-logo">
    <h1 style='margin:0;'>SkyGrid Solar AI v6.5</h1>
</div>""", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📊 МОНІТОРИНГ ТА АНАЛІЗ", "🌦 ПОГОДА В НІКОПОЛІ"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    s_today = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['Power_MW'].sum()
    s_tomorrow = df_forecast[df_forecast['Time'].dt.date == (now_ua + timedelta(days=1)).date()]['Power_MW'].sum()
    
    c1.metric("СЬОГОДНІ", f"{s_today:.1f} MWh")
    c2.metric("ЗАВТРА", f"{s_tomorrow:.1f} MWh")
    c3.metric("ТОЧНІСТЬ ШІ", f"{accuracy:.1f} %")
    c4.metric("КОЕФІЦІЄНТ (BIAS)", f"{ai_bias:.2f}x")

    # Основний графік
    st.markdown("---")
    df_p = df_forecast[df_forecast['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_p['Time'], y=df_p['Power_MW'], fill='tozeroy', name="Корегований План", line=dict(color='#00ff7f', width=3)))
    fig.update_layout(height=350, template="plotly_dark", margin=dict(l=0,r=0,t=20,b=0))
    st.plotly_chart(fig, use_container_width=True)

    # Таблиця порівняння для контролю
    if df_history is not None:
        with st.expander("🔍 Детальний аналіз План-Факт за останні дні"):
            df_v = df_history.dropna(subset=['Fact_MW', 'Forecast_MW']).tail(15).copy()
            df_v['Відхилення %'] = ((df_v['Fact_MW'] - df_v['Forecast_MW']) / df_v['Forecast_MW'] * 100).round(1)
            st.dataframe(df_v.style.format({'Fact_MW': '{:.2f}', 'Forecast_MW': '{:.2f}'}), use_container_width=True)

    # Кнопка Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_ex = df_p[['Time', 'Power_MW']].copy()
        df_ex.columns = ['Дата/Час', 'План МВт']
        df_ex.to_excel(writer, index=False)
    st.download_button("📥 Завантажити план в Excel", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d%m')}.xlsx")

with tab2:
    # Твоя класична сторінка погоди (без змін)
    df_t = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]
    if not df_t.empty:
        cur = df_t[df_t['Time'].dt.hour == now_ua.hour].iloc[0] if now_ua.hour in df_t['Time'].dt.hour.values else df_t.iloc[0]
        st.markdown(f"<h1 style='text-align: center;'>Прогноз погоди на {now_ua.strftime('%d.%m.%Y')}</h1>", unsafe_allow_html=True)
        col_l, col_r = st.columns([1, 2])
        with col_l:
            st.markdown(f"""<div style='background:rgba(255,255,255,0.05); padding:30px; border-radius:20px; border:1px solid rgba(255,255,255,0.1); text-align:center;'>
                <p style='font-size:70px; margin:0;'>⛅</p>
                <p style='font-size:40px; font-weight:bold; margin:0;'>{cur['Temp']:.1f}°C</p>
                <p style='color:gray;'>Хмарність: {cur['Clouds']:.0f}%</p>
            </div>""", unsafe_allow_html=True)
        with col_r:
            st.area_chart(df_t.set_index('Time')[['Radiation']], color="#FFD700")
