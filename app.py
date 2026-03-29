import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime
import time
import pytz
import io
from sklearn.ensemble import RandomForestRegressor

# 1. Конфігурація
st.set_page_config(page_title="SkyGrid Solar AI v16.1", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
    except:
        return None, None, "No API Key"
    
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob,conditions,icon&key={api_key}&contentType=json"
    
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list, d_list = [], []
            for d in data['days']:
                d_list.append({'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'), 'Умови': d.get('conditions')})
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': hr.get('solarradiation', 0),
                        'CloudCover': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0),
                        'WindSpeed': hr.get('windspeed', 0),
                        'PrecipProb': hr.get('precipprob', 0)
                    })
            return pd.DataFrame(h_list), d_list, "OK"
    except: pass
    return None, None, "Error"

def train_solar_model(df_base):
    # Колонки, які ми хочемо бачити
    target_cols = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    
    # Використовуємо тільки ті колонки, що реально є в CSV
    available_features = [c for c in target_cols if c in df_train.columns]
    
    if len(df_train) < 10:
        return None, None, []

    X = df_train[available_features].fillna(df_train.mean(numeric_only=True))
    y = df_train['Fact_MW']
    
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    importance = dict(zip(available_features, model.feature_importances_))
    return model, importance, available_features

# --- ОСНОВНА ЛОГІКА ---
df_f, day_forecast, status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    
    model, importance, model_features = train_solar_model(df_h)
    
    if model and df_f is not None:
        # Створюємо базовий прогноз
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        
        # Створюємо вхідний набір даних, який ТОЧНО відповідає моделі
        X_input = df_f[model_features].copy() if all(c in df_f.columns for c in model_features) else df_f[['Forecast_MW']]
        
        # Якщо якихось колонок не вистачає в прогнозі погоди, додаємо їх як 0
        for col in model_features:
            if col not in X_input.columns:
                X_input[col] = 0
        
        # Важливо: порядок колонок має бути як при навчанні
        X_input = X_input[model_features]
        
        df_f['AI_MW'] = model.predict(X_input.fillna(0))
        model_status = "AI Active"
    elif df_f is not None:
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        df_f['AI_MW'] = df_f['Forecast_MW']
        model_status = "Basic Mode"
except Exception as e:
    st.error(f"Помилка: {e}")
    model_status = "Error"

# --- ВІЗУАЛІЗАЦІЯ ---
st.title("☀️ SkyGrid Solar AI")
st.caption(f"Статус: {model_status} | База: {len(df_h) if 'df_h' in locals() else 0} записів")

if df_f is not None:
    t1, t2 = st.tabs(["📊 ПРОГНОЗ", "🧠 АНАЛІЗ"])
    
    with t1:
        today_data = df_f[df_f['Time'].dt.date == now_ua.date()]
        st.metric("ПРОГНОЗ НА СЬОГОДНІ", f"{today_data['AI_MW'].sum():.1f} MWh")
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Forecast_MW'], name="План (Сирий)", line=dict(dash='dash')))
        fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['AI_MW'], name="AI Корекція", fill='tozeroy'))
        fig.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)

    with t2:
        if 'importance' in locals() and importance:
            st.write("### Важливість факторів для моделі")
            imp_df = pd.DataFrame(list(importance.items()), columns=['Параметр', 'Вплив']).sort_values('Вплив')
            st.plotly_chart(px.bar(imp_df, x='Вплив', y='Параметр', orientation='h'))
