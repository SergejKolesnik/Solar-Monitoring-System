import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime, timedelta
import time, pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI v18.1", layout="wide")
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

# 2. ДАНІ ТА ШІ
try:
    v = int(time.time() / 60)
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time'].astype(str).str.replace('DST', '').str.strip())
    
    from sklearn.ensemble import RandomForestRegressor
    df_train = df_h.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    if len(df_train) > 24:
        model = RandomForestRegressor(n_estimators=100, max_depth=8).fit(df_train[features].fillna(0), df_train['Fact_MW'])
        model_acc = 100 * model.score(df_train[features].fillna(0), df_train['Fact_MW'])
        if df_f is not None:
            df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
    else:
        model_acc, model = 0, None
        if df_f is not None: 
            df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
            df_f['AI_MW'] = df_f['Forecast_MW']
except:
    df_h, model_acc, model = pd.DataFrame(), 0, None

# 3. ІНТЕРФЕЙС
st.title("☀️ SkyGrid Solar AI v18.1")
st.caption(f"АТ «НЗФ» • С.І. Колесник • {now_ua.strftime('%d.%m.%Y %H:%M')}")

t1, t2, t3, t4 = st.tabs(["📊 МОНІТОРИНГ", "🌦 МЕТЕОЦЕНТР", "🧠 НАВЧАННЯ ШІ", "📑 БАЗА ДАНИХ"])

with t1:
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d_date = (now_ua + timedelta(days=i)).date()
        if df_f is not None:
            d_data = df_f[df_f['Time'].dt.date == d_date]
            if not d_data.empty:
                col.metric(f"{d_date.strftime('%d.%m')}", f"{d_data['AI_MW'].sum():.1f} MWh", f"Точність: {model_acc:.1f}%")
    
    if df_f is not None:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), name="Сайт", line=dict(dash='dot', color='gray')))
        fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['AI_MW'].head(72), name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
        st.plotly_chart(fig, use_container_width=True)

with t2:
    if day_forecast:
        st.write("### Детальний прогноз по днях")
        st.dataframe(pd.DataFrame(day_forecast), hide_index=True, use_container_width=True)

with t3:
    st.subheader(f"Статус навчання моделі: {model_acc:.1f}%")
    if not df_h.empty and model is not None:
        st.write("### 🔥 Теплова карта відхилень")
        hist = df_h.tail(168).copy()
        try:
            hist['AI_MW'] = model.predict(hist[features].fillna(0))
            hist['Error'] = hist['Fact_MW'] - hist['AI_MW']
            pivot = hist[hist['Hour'].between(7,19)].pivot(index='Time', columns='Hour', values='Error')
            st.plotly_chart(px.imshow(pivot, color_continuous_scale="RdBu_r", aspect="auto"), use_container_width=True)
        except: st.info("Карта буде доступна після оновлення бази.")

with t4:
    st.dataframe(df_h.tail(100), use_container_width=True)
