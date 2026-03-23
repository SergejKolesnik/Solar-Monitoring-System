import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI v14.0", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

if 'weather_cache' not in st.session_state: st.session_state.weather_cache = None

@st.cache_data(ttl=1800)
def fetch_weather():
    api_key = st.secrets["WEATHER_API_KEY"]
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,tempmax,tempmin,cloudcover,solarradiation,windspeed,winddir,precipprob,conditions,icon&key={api_key}&contentType=json"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            h_list, d_list = [], []
            for d in data['days']:
                d_list.append({
                    'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'),
                    'Макс': d.get('tempmax'),
                    'Мін': d.get('tempmin'),
                    'Опади': d.get('precipprob'),
                    'Вітер': d.get('windspeed'),
                    'Напрямок': d.get('winddir'),
                    'Умови': d.get('conditions'),
                    'Icon': d.get('icon', 'clear-day')
                })
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': hr.get('solarradiation', 0),
                        'Clouds': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0),
                        'WindSpd': hr.get('windspeed', 0)
                    })
            df = pd.DataFrame(h_list)
            return df, d_list, "OK"
        return None, None, f"API Error {res.status_code}"
    except Exception as e: return None, None, str(e)

# 2. ДАНІ
df_raw, day_forecast, status = fetch_weather()
if df_raw is None and st.session_state.weather_cache:
    df_f, day_forecast = st.session_state.weather_cache
else:
    df_f = df_raw
    st.session_state.weather_cache = (df_raw, day_forecast)

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias, exp_hours = 1.0, 0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    df_h['Time'] = pd.to_datetime(df_h['Time'])
    # Уніфікація назв колонок
    if 'CloudCover' in df_h.columns: df_h = df_h.rename(columns={'CloudCover': 'Clouds'})
    
    df_h = df_h[(df_h['Time'].dt.year == 2026) & (df_h['Time'].dt.month == 3)]
    exp_hours = len(df_h.dropna(subset=['Fact_MW']))
    
    df_v = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).tail(72)
    if not df_v.empty: ai_bias = df_v['Fact_MW'].sum() / df_v['Forecast_MW'].sum()
    
    df_h['Date'] = df_h['Time'].dt.date
    daily_stats = df_h.groupby('Date').agg({'Fact_MW':'sum','Forecast_MW':'sum'}).reset_index()
except: daily_stats = pd.DataFrame()

# 3. ЛОГІКА ПРОГНОЗУ
st.sidebar.header("⚙️ Керування")
boost = st.sidebar.slider("Ручна корекція (%)", 50, 300, 100) / 100
final_bias = ai_bias * boost
df_f['AI_MW'] = df_f['Rad'] * 11.4 * 0.001 * final_bias

# 4. ВЕРСТКА
st.markdown(f"""<div style="display:flex; align-items:center; margin-bottom:20px;">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:60px; border-radius:10px; margin-right:20px;">
    <div>
        <h1 style='margin:0; font-size:32px;'>SkyGrid Solar AI v14.0</h1>
        <p style='margin:0; color:gray;'>Локація: Нікополь (NZF) • Точне спостереження</p>
    </div>
</div>""", unsafe_allow_html=True)

t1, t2 = st.tabs(["📊 АНАЛІТИКА ТА ПРОГНОЗ", "🌦 МЕТЕОЦЕНТР НІКОПОЛЬ"])

with t1:
    st.markdown(f"#### 📅 Прогноз на сьогодні: **{now_ua.strftime('%d.%m.%Y')}**")
    c1, c2, c3, c4 = st.columns(4)
    s_ai = df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
    c1.metric("ПРОГНОЗ AI (СЬОГОДНІ)", f"{s_ai:.1f} MWh", delta=f"{final_bias:.2f}x")
    c2.metric("БАЗА ДОСВІДУ", f"{exp_hours} год", help="Кількість годин з фактом АСКОЕ в базі")
    c3.metric("КОЕФІЦІЄНТ AI", f"{ai_bias:.2f}x")
    c4.metric("РУЧНИЙ БУСТ", f"{boost:.2f}x")

    # Основний графік
    if not daily_stats.empty:
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f', text=daily_stats['Fact_MW'].round(1), textposition='outside'))
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW']*final_bias, name="План AI", marker_color='#1f77b4'))
        fig_d.update_layout(barmode='group', height=350, template="plotly_dark", margin=dict(l=0,r=0,t=30,b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig_d, use_container_width=True)

    with st.expander("🧠 AI Training Center (Heatmap Похибок)"):
        if not df_h.empty:
            df_heat = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
            if not df_heat.empty:
                df_heat['Hour'] = df_heat['Time'].dt.hour
                df_heat['Day'] = df_heat['Time'].dt.strftime('%d.%m')
                df_heat['Error'] = df_heat['Fact_MW'] - (df_heat['Forecast_MW'] * ai_bias)
                pivot = df_heat[(df_heat['Hour']>=6) & (df_heat['Hour']<=19)].pivot(index='Day', columns='Hour', values='Error')
                fig_hm = px.imshow(pivot, color_continuous_scale="RdBu_r", aspect="auto", origin='lower')
                fig_hm.update_layout(height=350, template="plotly_dark")
                st.plotly_chart(fig_hm, use_container_width=True)

with t2:
    st.subheader("🌦 Прогноз погоди: Нікополь (10 днів)")
    
    # 1. ШТОРМОВІ ПОПЕРЕДЖЕННЯ
    if day_forecast:
        alert_cols = st.columns(len(day_forecast[:4]))
        for i, d in enumerate(day_forecast[:4]):
            if d['Вітер'] > 13:
                alert_cols[i].error(f"💨 **{d['Дата']}**\n\nВітер {d['Вітер']} м/с")
            elif d['Опади'] > 70:
                alert_cols[i].warning(f"🌧 **{d['Дата']}**\n\nЗлива {d['Опади']}%")

    # 2. ПЛИТОЧКИ ПРОГНОЗУ (Horizontal Ribbon)
    st.markdown("---")
    def get_icon(name):
        icons = {"rain": "🌧️", "cloudy": "☁️", "partly-cloudy-day": "⛅", "clear-day": "☀️", "snow": "❄️", "wind": "💨"}
        return icons.get(name, "🌡️")

    cols = st.columns(10)
    for i, d in enumerate(day_forecast):
        with cols[i]:
            bg_color = "rgba(255, 75, 75, 0.1)" if d['Вітер'] > 13 else "rgba(255, 255, 255, 0.05)"
            st.markdown(f"""
                <div style='background:{bg_color}; padding:12px; border-radius:12px; text-align:center; border:1px solid rgba(255,255,255,0.1);'>
                    <p style='margin:0; font-size:14px; color:gray;'>{d['Дата']}</p>
                    <p style='margin:5px 0; font-size:28px;'>{get_icon(d['Icon'])}</p>
                    <p style='margin:0; font-weight:bold; font-size:18px;'>{d['Макс']:.0f}°</p>
                    <p style='margin:0; font-size:12px; color:#00d4ff;'>{d['Вітер']:.1f} м/с</p>
                </div>
            """, unsafe_allow_html=True)

    # 3. ДЕТАЛЬНА ТАБЛИЦЯ ТА ТРЕНД
    st.markdown("### 📊 Деталі та вітровий режим")
    c_left, c_right = st.columns([1, 1])
    
    with c_left:
        def wind_to_text(deg):
            dirs = ["↑ Пн", "↗ Пн-Сх", "→ Сх", "↘ Пд-Сх", "↓ Пд", "↙ Пд-Зх", "← Зх", "↖ Пн-Зх"]
            return dirs[int((deg + 22.5) % 360 // 45)]
        
        df_10 = pd.DataFrame(day_forecast)
        df_10['Напр.'] = df_10['Напрямок'].apply(wind_to_text)
        st.dataframe(df_10[['Дата', 'Умови', 'Мін', 'Макс', 'Опади', 'Вітер', 'Напр.']], hide_index=True, use_container_width=True)

    with c_right:
        fig_w = go.Figure()
        fig_w.add_trace(go.Bar(x=df_10['Дата'], y=df_10['Вітер'], name="Вітер м/с", marker_color='#00d4ff'))
        fig_w.add_trace(go.Scatter(x=df_10['Дата'], y=df_10['Опади'], name="Опади %", yaxis="y2", line=dict(color='#ff4b4b')))
        fig_w.update_layout(height=280, template="plotly_dark", yaxis2=dict(overlaying='y', side='right', range=[0,100]), 
                          margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_w, use_container_width=True)
