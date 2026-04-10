import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time, pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar Monitoring", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Forecast_MW': hr.get('solarradiation', 0) * 11.4 * 0.001
                    })
            return pd.DataFrame(h_list)
    except: return None

df_f = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 2. ЗАВАНТАЖЕННЯ БАЗИ
try:
    v = int(time.time() / 60)
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time'])
except:
    df_h = pd.DataFrame()

# 3. ІНТЕРФЕЙС
st.title("☀️ SkyGrid Solar AI (Base Version)")
st.write(f"Останнє оновлення: {now_ua.strftime('%d.%m %H:%M')}")

if df_f is not None:
    st.subheader("Графік генерації (План)")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), 
                             name="Прогноз (МВт)", fill='tozeroy', line=dict(color='#00ff7f')))
    st.plotly_chart(fig, use_container_width=True)

if not df_h.empty:
    st.subheader("Останні дані з бази АСКОЕ")
    st.dataframe(df_h.tail(20), use_container_width=True)
else:
    st.error("База даних не завантажена. Перевірте файл solar_ai_base.csv на GitHub.")
