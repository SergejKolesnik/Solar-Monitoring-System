import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time, pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI v18.2", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')
st.markdown("<style>.stApp {background-color: #0E1117; color: white;}</style>", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,tempmax,tempmin,cloudcover,solarradiation&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list, d_list = [], []
            for d in data['days']:
                d_list.append({'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'), 'Макс': d.get('tempmax'), 'Умови': d.get('conditions')})
                for hr in d['hours']:
                    h_list.append({'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Hour': int(hr['datetime'].split(':')[0]), 'Rad': hr.get('solarradiation', 0),
                        'CloudCover': hr.get('cloudcover', 0), 'Temp': hr.get('temp', 0)})
            return pd.DataFrame(h_list), d_list
    except: pass
    return None, None

df_f, day_forecast = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 2. БЕЗПЕЧНЕ ЗАВАНТАЖЕННЯ ДАНИХ
df_h = pd.DataFrame()
model_acc = 0
try:
    v = int(time.time() / 60)
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time'], errors='coerce')
    # Очистка від порожніх рядків, щоб не було IndexError
    df_h = df_h.dropna(subset=['Time'])
except: pass

# 3. ІНТЕРФЕЙС
st.title("☀️ SkyGrid Solar AI")
st.caption(f"Статус: Робочий • {now_ua.strftime('%H:%M')}")

t1, t2, t3, t4 = st.tabs(["📊 МОНІТОРИНГ", "🌦 МЕТЕО", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with t1:
    if df_f is not None:
        # Показуємо графік прогнозу, він працює незалежно від бази
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=(df_f['Rad'].head(72)*11.4*0.001), 
                                 name="Прогноз станції (МВт)", fill='tozeroy', line=dict(color='#00ff7f')))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Помилка завантаження погоди. Перевірте API ключ.")

with t4:
    if not df_h.empty:
        st.write("Останні 20 записів з бази:")
        st.dataframe(df_h.tail(20), use_container_width=True)
    else:
        st.info("База даних АСКОЕ порожня або ще не синхронізована.")

with t3:
    st.info("Система очікує стабільного потоку даних для активації ШІ.")
