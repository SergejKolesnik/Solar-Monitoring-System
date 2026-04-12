import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime, timedelta
import time, pytz

# Імпорт нашого нового блоку навчання
from model_engine import train_and_predict

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI v20.0", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')
st.markdown("<style>.stApp {background-color: #0E1117; color: white;}</style>", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,tempmax,tempmin,cloudcover,solarradiation,windspeed,precipprob,conditions,icon&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list, d_list = [], []
            for d in data['days']:
                d_list.append({
                    'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'),
                    'Макс': d.get('tempmax'), 'Мін': d.get('tempmin'),
                    'Опади': d.get('precipprob'), 'Вітер': d.get('windspeed'),
                    'Умови': d.get('conditions')
                })
                for hr in d['hours']:
                    h_list.append({'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Hour': int(hr['datetime'].split(':')[0]), 'Rad': hr.get('solarradiation', 0),
                        'CloudCover': hr.get('cloudcover', 0), 'Temp': hr.get('temp', 0),
                        'WindSpeed': hr.get('windspeed', 0), 'PrecipProb': hr.get('precipprob', 0)})
            return pd.DataFrame(h_list), d_list
    except: pass
    return None, None

df_f, day_forecast = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 2. ЗАВАНТАЖЕННЯ БАЗИ ТА ВИКЛИК ШІ
try:
    v = int(time.time() / 60)
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time']).dt.floor('h')
    
    if df_f is not None:
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        # Виклик функції з model_engine.py
        ai_preds, model_acc = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds
        # Обнулення нічних годин
        df_f.loc[(df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20), 'AI_MW'] = 0
    else: model_acc = 0
except:
    df_h, model_acc = pd.DataFrame(), 0

# 3. ІНТЕРФЕЙС
st.title(f"☀️ SkyGrid Solar AI (Точність: {model_acc:.1f}%)")
st.caption(f"АТ «НЗФ» • С.І. Колесник • {now_ua.strftime('%d.%m.%Y %H:%M')}")

tabs = st.tabs(["📊 МОНІТОРИНГ", "🌦 МЕТЕОЦЕНТР", "🧠 ДІАГНОСТИКА ШІ", "📑 БАЗА ДАНИХ"])

with tabs[0]:
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d_date = (now_ua + timedelta(days=i)).date()
        if df_f is not None:
            d_data = df_f[df_f['Time'].dt.date == d_date]
            if not d_data.empty:
                col.metric(f"{d_date.strftime('%d.%m')}", f"{d_data['AI_MW'].sum():.1f} MWh", f"Сайт: {d_data['Forecast_MW'].sum():.1f}")
    
    if df_f is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), name="Прогноз сайту", line=dict(dash='dot', color='gray')))
        fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['AI_MW'].head(72), name="План ШІ (коригований)", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
        st.plotly_chart(fig, use_container_width=True)

with tabs[1]:
    if day_forecast:
        st.table(pd.DataFrame(day_forecast))

with tabs[2]:
    st.write("### Аналіз навчання")
    st.info("ШІ використовує RandomForestRegressor для корекції метеорологічних даних на основі історичного факту АСКОЕ.")
    if model_acc > 0:
        st.success(f"Модель успішно навчена на базі {len(df_h)} записів.")

with tabs[3]:
    st.dataframe(df_h.tail(50), use_container_width=True)
