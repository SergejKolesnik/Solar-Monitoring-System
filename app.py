import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime, timedelta
import time, pytz

# КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI v19.3", layout="wide")
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

# ПІДГОТОВКА БАЗИ
try:
    v = int(time.time() / 60)
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time'].astype(str).str.replace('DST', '').str.strip())
    
    from sklearn.ensemble import RandomForestRegressor
    df_train = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    df_train = df_train[df_train['Fact_MW'] > 0]
    
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    if df_f is not None:
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        if len(df_train) > 24:
            model = RandomForestRegressor(n_estimators=100, max_depth=8).fit(df_train[features].fillna(0), df_train['Fact_MW'])
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
            model_acc = 100 * model.score(df_train[features].fillna(0), df_train['Fact_MW'])
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            model_acc = 0
except:
    df_h = pd.DataFrame()
    model_acc = 0

# ІНТЕРФЕЙС
st.title("☀️ SkyGrid Solar AI v19.3")
st.caption(f"АТ «НЗФ» • С.І. Колесник • {now_ua.strftime('%d.%m.%Y %H:%M')}")

if df_f is None:
    st.error("Помилка отримання метеоданих.")
    st.stop()

t1, t2, t3, t4 = st.tabs(["📊 МОНІТОРИНГ", "🌦 МЕТЕО", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with t1:
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d_date = (now_ua + timedelta(days=i)).date()
        d_data = df_f[df_f['Time'].dt.date == d_date]
        if 'AI_MW' in d_data.columns:
            col.metric(f"{d_date.strftime('%d.%m')}", f"{d_data['AI_MW'].sum():.1f} MWh", f"Сайт: {d_data['Forecast_MW'].sum():.1f}")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), name="Сайт", line=dict(dash='dot', color='gray')))
    if 'AI_MW' in df_f.columns:
        fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['AI_MW'].head(72), name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    st.plotly_chart(fig, use_container_width=True)

with t2:
    if day_forecast:
        st.dataframe(pd.DataFrame(day_forecast), hide_index=True, use_container_width=True)

with t3:
    st.subheader(f"Точність: {model_acc:.1f}%")
    if not df_h.empty and 'Fact_MW' in df_h.columns:
        st.write("### 🔥 Теплова карта похибок (Факт - Сайт)")
        hist = df_h.tail(168).copy()
        hist['Error'] = hist['Fact_MW'] - hist['Forecast_MW']
        pivot = hist[hist['Hour'].between(7,19)].pivot(index='Time', columns='Hour', values='Error')
        st.plotly_chart(px.imshow(pivot, color_continuous_scale="RdBu_r"), use_container_width=True)

with t4:
    st.dataframe(df_h.tail(50), use_container_width=True)
