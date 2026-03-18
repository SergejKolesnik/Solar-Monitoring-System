import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v8.2", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def get_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        lat, lon = "47.56", "34.39"
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat}/{lon}/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation&include=hours,days&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        if res.status_code != 200: return "API Error"
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
    except: return "Connection Error"

def get_icon(clouds):
    return "☀️" if clouds < 30 else "⛅" if clouds < 70 else "☁️"

# 2. АНАЛІТИКА ТА РОЗРАХУНКИ
df_forecast = get_weather_data()
if isinstance(df_forecast, str): st.error(f"⚠️ {df_forecast}: Сервер погоди тимчасово недоступний. Спробуйте оновити сторінку."); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias = 1.0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_history = pd.read_csv(repo_url)
    df_history['Time'] = pd.to_datetime(df_history['Time'])
    
    # Розрахунок Bias по останніх 3-х днях
    df_v = df_history.dropna(subset=['Fact_MW', 'Forecast_MW'])
    if not df_v.empty:
        df_recent = df_v[df_v['Time'] > (now_ua - timedelta(days=3))]
        if not df_recent.empty:
            ai_bias = df_recent['Fact_MW'].sum() / df_recent['Forecast_MW'].sum()
            
    df_history['Date'] = df_history['Time'].dt.date
    daily_stats = df_history.groupby('Date').agg({'Fact_MW': 'sum', 'Forecast_MW': 'sum'}).reset_index()
    daily_stats = daily_stats.tail(7)
except: daily_stats = pd.DataFrame()

# Розрахунок двох типів прогнозу
df_forecast['Raw_MW'] = df_forecast['Radiation'] * 11.4 * 0.001
df_forecast['AI_MW'] = df_forecast['Raw_MW'] * ai_bias

# 3. ІНТЕРФЕЙС
st.markdown("""
    <style>
    .nzf-logo { width: 55px; border-radius: 8px; margin-right: 15px; }
    .main-header { display: flex; align-items: center; margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

st.markdown(f"""<div class="main-header">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" class="nzf-logo">
    <h1 style='margin:0;'>SkyGrid Solar AI <span style='color:#00ff7f; font-size:16px;'>v8.2</span></h1>
</div>""", unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
s_ai = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
s_raw = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]['Raw_MW'].sum()

c1.metric("ОЦІНКА SKYGRID (AI)", f"{s_ai:.1f} MWh")
c2.metric("ПРОГНОЗ VISUAL CROSSING", f"{s_raw:.1f} MWh")
c3.metric("КОЕФІЦІЄНТ AI", f"{ai_bias:.2f}x")
c4.metric("СТАТУС", "Online")

tab1, tab2 = st.tabs(["📊 ПОРІВНЯННЯ ТА АНАЛІЗ", "🌦 МЕТЕОУМОВИ"])

with tab1:
    st.subheader("📅 Історія порівняння: Метео vs SkyGrid (AI) vs Факт")
    if not daily_stats.empty:
        fig_d = go.Figure()
        # Прогноз Visual Crossing (Сірий)
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW'], name="Прогноз Visual Crossing", marker_color='#666'))
        # Оцінка AI (Синій)
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW']*ai_bias, name="Оцінка SkyGrid (AI)", marker_color='#1f77b4'))
        # Факт АСКОЕ (Зелений)
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f', text=daily_stats['Fact_MW'].round(1), textposition='outside'))
        
        fig_d.update_layout(barmode='group', height=380, template="plotly_dark", margin=dict(l=0,r=0,t=30,b=0), xaxis=dict(type='category'))
        st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("---")
    st.subheader("⏱ Оперативний графік на 72 години")
    
    df_p = df_forecast[df_forecast['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    daily_sums_ai = df_p.groupby(df_p['Time'].dt.date)['AI_MW'].sum()
    daily_sums_raw = df_p.groupby(df_p['Time'].dt.date)['Raw_MW'].sum()
    
    fig_h = go.Figure()
    fig_h.add_trace(go.Scatter(x=df_p['Time'], y=df_p['AI_MW'], fill='tozeroy', name="AI Оцінка (МВт)", line=dict(color='#00ff7f', width=3)))
    fig_h.add_trace(go.Scatter(x=df_p['Time'], y=df_p['Raw_MW'], name="Метео Прогноз (МВт)", line=dict(color='gray', width=1, dash='dot')))
    
    for date, t_ai in daily_sums_ai.items():
        t_raw = daily_sums_raw[date]
        fig_h.add_annotation(
            x=f"{date} 12:00:00", y=df_p[df_p['Time'].dt.date == date]['AI_MW'].max() + 0.4,
            text=f"<b>AI: {t_ai:.1f} | Метео: {t_raw:.1f} MWh</b>", showarrow=False, font=dict(color="#FFD700", size=12),
            bgcolor="rgba(0,0,0,0.7)", bordercolor="#FFD700", borderpad=4
        )
        
    fig_h.update_layout(height=380, template="plotly_dark", margin=dict(l=0,r=0,t=40,b=0))
    st.plotly_chart(fig_h, use_container_width=True)

    # Експорт Excel
    st.markdown("### 📥 Експорт даних")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_ex = df_p[['Time', 'AI_MW', 'Raw_MW']].copy()
        df_ex.columns = ['Дата/Час', 'Оцінка AI (МВт)', 'Прогноз Метео (МВт)']
        df_ex.to_excel(writer, index=False)
    st.download_button(label="💾 Завантажити прогноз в Excel", data=output.getvalue(), file_name=f"Solar_AI_v8.2.xlsx")

with tab2:
    # Друга сторінка (фіксована v4.6)
    df_t = df_forecast[df_forecast['Time'].dt.date == now_ua.date()]
    if not df_t.empty:
        cur = df_t[df_t['Time'].dt.hour == now_ua.hour].iloc[0] if now_ua.hour in df_t['Time'].dt.hour.values else df_t.iloc[0]
        st.markdown(f"<h3 style='text-align:center;'>Нікополь: {now_ua.strftime('%d.%m.%Y')}</h3>", unsafe_allow_html=True)
        col_l, col_r = st.columns([1, 2])
        with col_l:
            st.markdown(f"""<div style='background:rgba(255,255,255,0.05); padding:30px; border-radius:15px; border:1px solid rgba(255,255,255,0.1); text-align:center;'>
                <p style='font-size:70px; margin:0;'>{get_icon(cur['Clouds'])}</p>
                <p style='font-size:40px; font-weight:bold; margin:0;'>{cur['Temp']:.1f}°C</p>
                <p style='color:gray;'>Хмарність: {cur['Clouds']:.0f}%</p>
            </div>""", unsafe_allow_html=True)
        with col_r:
            st.area_chart(df_t.set_index('Time')[['Radiation']], color="#FFD700", height=230)
