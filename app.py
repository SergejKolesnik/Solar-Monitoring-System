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
st.set_page_config(page_title="SkyGrid: Solar AI v13.1", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

if 'weather_cache' not in st.session_state: st.session_state.weather_cache = None

@st.cache_data(ttl=1800)
def fetch_weather():
    api_key = st.secrets["WEATHER_API_KEY"]
    # Запит на 10 днів
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,tempmax,tempmin,cloudcover,solarradiation,windspeed,winddir,precipprob,conditions&key={api_key}&contentType=json"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            d_list = []
            for d in data['days']:
                d_list.append({
                    'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'),
                    'Макс': d.get('tempmax'),
                    'Мін': d.get('tempmin'),
                    'Опади %': d.get('precipprob'),
                    'Вітер м/с': d.get('windspeed'),
                    'Напрямок': d.get('winddir'),
                    'Умови': d.get('conditions')
                })
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
            st.session_state.weather_cache = (df, d_list)
            return df, d_list, "OK"
        return None, None, f"API Error {res.status_code}"
    except Exception as e: return None, None, str(e)

# 2. ДАНІ
df_raw, day_forecast, status = fetch_weather()
if df_raw is None and st.session_state.weather_cache:
    df_f, day_forecast = st.session_state.weather_cache
else:
    df_f = df_raw

if df_f is None: st.error(f"📡 Збій зв'язку: {status}"); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias = 1.0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    df_h['Time'] = pd.to_datetime(df_h['Time'])
    
    # Виправляємо назви колонок для сумісності
    if 'CloudCover' in df_h.columns: df_h = df_h.rename(columns={'CloudCover': 'Clouds'})
    
    df_h = df_h[(df_h['Time'].dt.year == 2026) & (df_h['Time'].dt.month == 3)]
    df_v = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).tail(72)
    if not df_v.empty: ai_bias = df_v['Fact_MW'].sum() / df_v['Forecast_MW'].sum()
    
    df_h['Date'] = df_h['Time'].dt.date
    daily_stats = df_h.groupby('Date').agg({'Fact_MW':'sum','Forecast_MW':'sum'}).reset_index()
except: 
    df_h = pd.DataFrame(); daily_stats = pd.DataFrame()

# 3. ІНТЕРФЕЙС
st.sidebar.header("⚙️ Керування")
boost = st.sidebar.slider("Ручна корекція (%)", 50, 300, 100) / 100
final_bias = ai_bias * boost
df_f['AI_MW'] = df_f['Rad'] * 11.4 * 0.001 * final_bias

st.markdown(f"""<div style="display:flex; align-items:center; margin-bottom:15px;">
    <img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:55px; border-radius:8px; margin-right:15px;">
    <h1 style='margin:0;'>SkyGrid Solar AI v13.1</h1>
</div>""", unsafe_allow_html=True)

t1, t2 = st.tabs(["📊 АНАЛІТИКА ТА ПРОГНОЗ", "🌦 МЕТЕОЦЕНТР НІКОПОЛЬ"])

with t1:
    st.markdown(f"### 📅 Прогноз на сьогодні: **{now_ua.strftime('%d.%m.%Y')}**")
    c1, c2, c3, c4 = st.columns(4)
    s_ai = df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
    c1.metric("ОЦІНКА SKYGRID (AI)", f"{s_ai:.1f} MWh")
    c2.metric("КОЕФІЦІЄНТ AI", f"{ai_bias:.2f}x")
    c3.metric("РУЧНИЙ БУСТ", f"{boost:.2f}x")
    
    # Безпечний підрахунок досвіду
    exp_hours = len(df_h.dropna(subset=['Fact_MW'])) if not df_h.empty else 0
    c4.metric("БАЗА (ГОДИН)", exp_hours)

    if not daily_stats.empty:
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Fact_MW'], name="Факт", marker_color='#00ff7f'))
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW']*final_bias, name="План AI", marker_color='#1f77b4'))
        fig_d.update_layout(barmode='group', height=300, template="plotly_dark", margin=dict(l=0,r=0,t=20,b=0))
        st.plotly_chart(fig_d, use_container_width=True)

    with st.expander("🧠 AI Training Center"):
        if not df_h.empty and 'Fact_MW' in df_h.columns and 'Forecast_MW' in df_h.columns:
            df_heat = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
            if not df_heat.empty:
                df_heat['Hour'] = df_heat['Time'].dt.hour
                df_heat['Day'] = df_heat['Time'].dt.strftime('%d.%m')
                df_heat['Error'] = df_heat['Fact_MW'] - df_heat['Forecast_MW']
                pivot = df_heat[(df_heat['Hour']>=6) & (df_heat['Hour']<=19)].pivot(index='Day', columns='Hour', values='Error')
                fig_hm = px.imshow(pivot, color_continuous_scale="RdBu_r", aspect="auto")
                fig_hm.update_layout(height=350, template="plotly_dark")
                st.plotly_chart(fig_hm, use_container_width=True)

with t2:
    st.subheader("🌦 Прогноз Нікополь на 10 днів")
    
    if day_forecast:
        # Перевірка аномалій
        for d in day_forecast[:3]:
            if d['Вітер м/с'] > 12: st.error(f"🚩 **{d['Дата']}**: Штормовий вітер! {d['Вітер м/с']} м/с")
            if d['Опади %'] > 75: st.warning(f"🌧 **{d['Дата']}**: Сильні опади ({d['Опади %']}%)")
            if d['Макс'] > 25: st.info(f"🔥 **{d['Дата']}**: Аномальна спека {d['Макс']}°C")

        # Переклад напрямків
        def wind_to_text(deg):
            dirs = ["↑ Пн", "↗ Пн-Сх", "→ Сх", "↘ Пд-Сх", "↓ Пд", "↙ Пд-Зх", "← Зх", "↖ Пн-Зх"]
            return dirs[int((deg + 22.5) % 360 // 45)]

        df_10 = pd.DataFrame(day_forecast)
        df_10['Напрямок'] = df_10['Напрямок'].apply(wind_to_text)
        
        # Вивід таблиці
        st.table(df_10[['Дата', 'Умови', 'Мін', 'Макс', 'Опади %', 'Вітер м/с', 'Напрямок']])
        
        # Графік
