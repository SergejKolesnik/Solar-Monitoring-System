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
st.set_page_config(page_title="SkyGrid: Solar AI v14.2", layout="wide")
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
    if 'CloudCover' in df_h.columns: df_h = df_h.rename(columns={'CloudCover': 'Clouds'})
    
    df_h = df_h[(df_h['Time'].dt.year == 2026) & (df_h['Time'].dt.month == 3)]
    exp_hours = len(df_h.dropna(subset=['Fact_MW']))
    
    df_v = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).tail(72)
    if not df_v.empty: ai_bias = df_v['Fact_MW'].sum() / df_v['Forecast_MW'].sum()
    
    df_h['Date'] = df_h['Time'].dt.date
    daily_stats = df_h.groupby('Date').agg({'Fact_MW':'sum','Forecast_MW':'sum'}).reset_index()
except: daily_stats = pd.DataFrame()

# 3. КЕРУВАННЯ
st.sidebar.header("⚙️ Керування")
boost = st.sidebar.slider("Ручна корекція (%)", 50, 300, 100) / 100
final_bias = ai_bias * boost
df_f['AI_MW'] = df_f['Rad'] * 11.4 * 0.001 * final_bias

# 4. ВЕРСТКА
st.markdown(f"""<div style="display:flex; align-items:center; margin-bottom:20px;">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:60px; border-radius:10px; margin-right:20px;">
    <div>
        <h1 style='margin:0; font-size:32px;'>SkyGrid Solar AI v14.2</h1>
        <p style='margin:0; color:gray;'>Нікополь • Енергомоніторинг NZF</p>
    </div>
</div>""", unsafe_allow_html=True)

t1, t2 = st.tabs(["📊 АНАЛІТИКА ТА ПРОГНОЗ", "🌦 МЕТЕОЦЕНТР НІКОПОЛЬ"])

with t1:
    st.markdown(f"#### 📅 Прогноз на сьогодні: **{now_ua.strftime('%d.%m.%Y')}**")
    c1, c2, c3, c4 = st.columns(4)
    s_ai = df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
    c1.metric("ПРОГНОЗ AI", f"{s_ai:.1f} MWh", delta=f"{final_bias:.2f}x")
    c2.metric("БАЗА ДОСВІДУ", f"{exp_hours} год
