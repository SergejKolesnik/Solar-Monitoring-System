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
st.set_page_config(page_title="SkyGrid Solar AI v16.0", layout="wide")
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
            data, h_list, d_list = res.json(), [], []
            for d in data['days']:
                d_list.append({'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'), 'Умови': d.get('conditions'), 'Icon': d.get('icon')})
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
    # Обираємо колонки, які ТОЧНО є в CSV
    cols = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    
    # Перевірка наявності всіх колонок
    available_cols = [c for c in cols if c in df_train.columns]
    if len(df_train) < 10 or 'Forecast_MW' not in available_cols:
        return None, None, []

    X = df_train[available_cols].fillna(df_train.mean(numeric_only=True))
    y = df_train['Fact_MW']
    
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    return model, dict(zip(available_cols, model.feature_importances_)), available_cols

# --- ЛОГІКА ---
df_f, day_forecast, status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
model_status = "Calculation Mode"

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    
    model, importance, model_features = train_solar_model(df_h)
    
    if model and df_f is not None:
        df_f['Raw_MW'] = df_f['Rad'] * 11.4 * 0.001
        
        # СТВОРЕННЯ ДАНИХ ДЛЯ AI (СТРОГА ВІДПОВІДНІСТЬ НАЗВ)
        X_input = pd.DataFrame()
        X_input['Forecast_MW'] = df_f['Raw_MW']
        X_input['CloudCover'] = df_f['CloudCover']
        X_input['Temp'] = df_f['Temp']
        X_input['WindSpeed'] = df_f['WindSpeed']
        X_input['PrecipProb'] = df_f['PrecipProb']
        
        # Залишаємо тільки ті колонки, на яких вчилася модель
        X_input = X_input[model_features]
        
        df_f['AI_MW'] = model.predict(X_input.fillna(0))
        model_status = "AI Engine Active"
    elif df_f is not None:
        df_f['Raw_MW'] = df_f['Rad'] * 11.4 * 0.001
        df_f['AI_MW'] = df_f['Raw_MW']
except Exception as e:
    st.error(f"AI Error: {e}")

# --- ІНТЕРФЕЙС ---
st.title("☀️ SkyGrid Solar AI")
st.caption(f"Статус: {model_status} | Останнє оновлення: {now_ua.strftime('%H:%M')}")

if df_f is not None:
    t1, t2, t3 = st.tabs(["📊 ПРОГНОЗ", "🌦 МЕТЕО", "🧠 АНАЛІЗ AI"])
    
    with t1:
        s_sum = df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
        st.metric("ПРОГНОЗ НА СЬОГОДНІ", f"{s_sum:.1f} MWh")
        
        df_plot = df_f[df_f['Time'] >= pd.Timestamp(now_ua.date())].head(24)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_plot['Time'], y=df_plot['Raw_MW'], name="Базовий", line=dict(dash='dash')))
        fig.add_trace(go.Scatter(x=df_plot['Time'], y=df_plot['AI_MW'], name="AI Корекція", fill='tozeroy'))
        fig.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)

    with t3:
        if 'importance' in locals() and importance:
            imp_df = pd.DataFrame(list(importance.items()), columns=['Параметр', 'Важливість']).sort_values('Важливість')
            st.plotly_chart(px.bar(imp_df, x='Важливість', y='Параметр', orientation='h', title="Вплив факторів на прогноз"))
else:
    st.error("Дані недоступні")
