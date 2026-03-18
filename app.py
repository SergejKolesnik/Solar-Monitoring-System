import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v9.5", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

if 'weather_cache' not in st.session_state: st.session_state.weather_cache = None

@st.cache_data(ttl=1800)
def fetch_weather():
    api_key = st.secrets["WEATHER_API_KEY"]
    # ОНОВЛЕНІ КООРДИНАТИ: 47.631494, 34.348690
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,winddir,precipprob&key={api_key}&contentType=json"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': hr.get('solarradiation', 0),
                        'Clouds': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0),
                        'WindSpd': hr.get('windspeed', 0),
                        'WindDir': hr.get('winddir', 0),
                        'RainProb': hr.get('precipprob', 0)
                    })
            df = pd.DataFrame(h_list)
            st.session_state.weather_cache = df
            return df, "OK"
        return None, f"API Error {res.status_code}"
    except Exception as e: return None, str(e)

# 2. ДАНІ ТА AI
df_raw, status = fetch_weather()
df_f = df_raw if df_raw is not None else st.session_state.weather_cache
if df_f is None: st.error(f"📡 Збій: {status}"); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias = 1.0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    df_h['Time'] = pd.to_datetime(df_h['Time'])
    
    # Розрахунок Bias
    df_v = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).tail(72)
    if not df_v.empty: ai_bias = df_v['Fact_MW'].sum() / df_v['Forecast_MW'].sum()
    
    df_h['Date'] = df_h['Time'].dt.date
    daily_stats = df_h.groupby('Date').agg({'Fact_MW':'sum','Forecast_MW':'sum'}).reset_index().tail(7)
except: 
    df_h = pd.DataFrame()
    daily_stats = pd.DataFrame()

# Керування
st.sidebar.header("⚙️ Керування SkyGrid")
boost = st.sidebar.slider("Ручна корекція (%)", 50, 300, 100) / 100
final_bias = ai_bias * boost

df_f['AI_MW'] = df_f['Rad'] * 11.4 * 0.001 * final_bias
df_f['Raw_MW'] = df_f['Rad'] * 11.4 * 0.001

# 3. ІНТЕРФЕЙС
st.markdown(f"""<div style="display:flex; align-items:center; margin-bottom:15px;">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:55px; border-radius:8px; margin-right:15px;">
    <h1 style='margin:0;'>SkyGrid Solar AI v9.5</h1>
</div>""", unsafe_allow_html=True)

t1, t2 = st.tabs(["📊 АНАЛІТИКА ТА ПРОГНОЗ", "🌦 МЕТЕОУМОВИ НІКОПОЛЬ"])

with t1:
    c1, c2, c3 = st.columns(3)
    s_ai = df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
    s_raw = df_f[df_f['Time'].dt.date == now_ua.date()]['Raw_MW'].sum()
    c1.metric("ОЦІНКА SKYGRID (AI)", f"{s_ai:.1f} MWh", delta=f"{final_bias:.2f}x")
    c2.metric("ПРОГНОЗ VISUAL CROSSING", f"{s_raw:.1f} MWh")
    c3.metric("АВТО-КОЕФІЦІЄНТ", f"{ai_bias:.2f}x")

    # ГРАФІК 1: Порівняння
    if not daily_stats.empty:
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW'], name="Сайт", marker_color='#666'))
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW']*final_bias, name="SkyGrid AI", marker_color='#1f77b4'))
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f', text=daily_stats['Fact_MW'].round(1), textposition='outside'))
        fig_d.update_layout(barmode='group', height=330, template="plotly_dark", margin=dict(l=0,r=0,t=30,b=0), xaxis=dict(type='category'))
        st.plotly_chart(fig_d, use_container_width=True)

    # --- НОВИЙ БЛОК: AI TRAINING CENTER ---
    with st.expander("🧠 AI Training Center (Прогрес навчання)"):
        if not df_h.empty and 'Fact_MW' in df_h.columns:
            df_err = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
            if not df_err.empty:
                df_err['Hour'] = df_err['Time'].dt.hour
                df_err['Error'] = df_err['Fact_MW'] - df_err['Forecast_MW']
                hourly_err = df_err.groupby('Hour')['Error'].mean().reset_index()
                
                fig_err = go.Figure()
                fig_err.add_trace(go.Bar(x=hourly_err['Hour'], y=hourly_err['Error'], marker_color='#eb4034', name="Помилка МВт"))
                fig_err.update_layout(height=250, template="plotly_dark", title="Середня погодинна похибка (Факт - Прогноз)")
                st.plotly_chart(fig_err, use_container_width=True)
                st.caption("Цей графік показує, в які години метеосайт помиляється найбільше. ШІ використовує ці дані для майбутнього перенавчання.")

    st.markdown("---")
    df_p = df_f[df_f['Time'] >= pd.Timestamp(now_ua.date())].head(72)
    fig_h = go.Figure()
    fig_h.add_trace(go.Scatter(x=df_p['Time'], y=df_p['AI_MW'], fill='tozeroy', name="AI План", line=dict(color='#00ff7f', width=3)))
    sums = df_p.groupby(df_p['Time'].dt.date)['AI_MW'].sum()
    for date, val in sums.items():
        fig_h.add_annotation(x=f"{date} 12:00:00", y=df_p[df_p['Time'].dt.date == date]['AI_MW'].max()+0.5, text=f"Σ {val:.1f} MWh", showarrow=False, font=dict(color="#FFD700"))
    fig_h.update_layout(height=350, template="plotly_dark")
    st.plotly_chart(fig_h, use_container_width=True)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_p[['Time', 'AI_MW', 'Raw_MW']].to_excel(writer, index=False)
    st.download_button("📥 Скачати Excel", output.getvalue(), "Solar_Plan.xlsx")

with t2:
    # ПОВЕРНЕННЯ СТІЙКОГО ДИЗАЙНУ v4.6
    df_t = df_f[df_f['Time'].dt.date == now_ua.date()]
    if not df_t.empty:
        cur = df_t[df_t['Time'].dt.hour == now_ua.hour].iloc[0] if now_ua.hour in df_t['Time'].dt.hour.values else df_t.iloc[0]
        st.markdown(f"<h3 style='text-align:center;'>Нікополь: {now_ua.strftime('%d.%m.%Y %H:%M')}</h3>", unsafe_allow_html=True)
        col1, col2 = st.columns([1.2, 2])
        with col1:
            dirs = ["Пн", "Пн-Сх", "Сх", "Пд-Сх", "Пд", "Пд-Зх", "Зх", "Пн-Зх"]
            wind_txt = dirs[int((cur['WindDir'] + 22.5) % 360 // 45)]
            st.markdown(f"""<div style='background:rgba(255,255,255,0.05); padding:25px; border-radius:15px; border:1px solid rgba(255,255,255,0.1); text-align:center;'>
                <p style='font-size:70px; margin:0;'>☀️</p>
                <p style='font-size:45px; font-weight:bold; margin:0;'>{cur['Temp']:.1f}°C</p>
                <hr style='opacity:0.1; margin:15px 0;'>
                <div style='display:flex; justify-content:space-around;'>
                    <div><p style='color:gray; font-size:12px; margin:0;'>ВІТЕР</p><p style='font-size:18px; font-weight:bold; margin:0;'>{cur['WindSpd']:.1f} м/с</p><p style='font-size:12px; color:#00ff7f;'>{wind_txt}</p></div>
                    <div><p style='color:gray; font-size:12px; margin:0;'>ХМАРНІСТЬ</p><p style='font-size:18px; font-weight:bold; margin:0;'>{cur['Clouds']:.0f}%</p></div>
                    <div><p style='color:gray; font-size:12px; margin:0;'>ОПАДИ</p><p style='font-size:18px; font-weight:bold; margin:0;'>{cur['RainProb']:.0f}%</p></div>
                </div>
            </div>""", unsafe_allow_html=True)
        with col2:
            st.area_chart(df_t.set_index('Time')[['Rad']], color="#FFD700", height=255)
