import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time
import pytz
from sklearn.ensemble import RandomForestRegressor

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid AI v17.3: Training Monitor", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob,icon&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Hour': int(hr['datetime'].split(':')[0]),
                        'Rad': hr.get('solarradiation', 0),
                        'CloudCover': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0),
                        'WindSpeed': hr.get('windspeed', 0),
                        'PrecipProb': hr.get('precipprob', 0)
                    })
            return pd.DataFrame(h_list), "OK"
    except: pass
    return None, "Помилка API"

def train_solar_engine(df_base):
    # Підготовка даних
    df_base['Time'] = pd.to_datetime(df_base['Time'])
    df_base['Hour'] = df_base['Time'].dt.hour
    
    # Фільтр для навчання (тільки записи з фактом)
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    
    if len(df_train) < 20:
        return None, None, len(df_train)

    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    actual_features = [f for f in features if f in df_train.columns]
    
    X = df_train[actual_features].fillna(0)
    y = df_train['Fact_MW']
    
    model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    model.fit(X, y)
    
    importance = dict(zip(actual_features, model.feature_importances_))
    return model, importance, len(df_train)

# --- ЛОГІКА ЗАВАНТАЖЕННЯ ---
df_f, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    
    # Виправлення колонок
    if 'Clouds' in df_h.columns: df_h = df_h.rename(columns={'Clouds': 'CloudCover'})
    
    model, importance, data_count = train_solar_engine(df_h)
    
    if df_f is not None:
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        if model:
            features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
            df_f['AI_MW'] = df_f['AI_MW'].clip(lower=0)
            model_status = f"✅ ШІ активний (База: {data_count} год)"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            model_status = f"⏳ Навчання... (Потрібно ще {20 - data_count} год факту)"
except Exception as e:
    model_status = f"⚠️ Помилка: {e}"

# --- ІНТЕРФЕЙС ---
st.title("☀️ SkyGrid Solar AI v17.3")
st.info(f"Статус системи: {model_status}")

if df_f is not None:
    t1, t2, t3 = st.tabs(["📊 ПРОГНОЗ", "🧠 ПРОЦЕС НАВЧАННЯ", "📑 СИРІ ДАНІ"])
    
    with t1:
        st.write(f"### Погодинний план на сьогодні: {now_ua.strftime('%d.%m')}")
        fig_p = go.Figure()
        fig_p.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Forecast_MW'], name="Базовий план", line=dict(dash='dot', color='gray')))
        fig_p.add_trace(go.Scatter(x=df_f['Time'], y=df_f['AI_MW'], name="AI Корекція", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
        fig_p.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=20,b=0))
        st.plotly_chart(fig_p, use_container_width=True)

    with t2:
        if 'df_h' in locals() and not df_h.empty:
            st.write("### Аналіз точності (Останні 3 дні)")
            df_h['Time'] = pd.to_datetime(df_h['Time'])
            # Фільтруємо останні 72 години, де є Факт
            df_recent = df_h.dropna(subset=['Fact_MW']).tail(72)
            
            if not df_recent.empty:
                fig_l = go.Figure()
                fig_l.add_trace(go.Scatter(x=df_recent['Time'], y=df_recent['Forecast_MW'], name="Прогноз сайту", line=dict(color='orange')))
                fig_l.add_trace(go.Scatter(x=df_recent['Time'], y=df_recent['Fact_MW'], name="Реальний Факт", line=dict(color='#00ff7f', width=2)))
                fig_l.update_layout(template="plotly_dark", height=350, title="ШІ вчиться на різниці цих ліній")
                st.plotly_chart(fig_l, use_container_width=True)
                st.caption("💡 Чим більша розбіжність між лініями, тим більше ШІ має 'роботи' по корекції.")
            else:
                st.warning("В базі даних ще немає записів з фактичною генерацією (Fact_MW).")

    with t3:
        st.write("### Останні 15 записів з репозиторію")
        if 'df_h' in locals():
            st.dataframe(df_h.tail(15), use_container_width=True)

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.О. Колесник & SkyGrid AI</div>", unsafe_allow_html=True)
