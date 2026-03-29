import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime
import time
import pytz
from sklearn.ensemble import RandomForestRegressor

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid AI v17.0: Hourly Analysis", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
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

def train_advanced_model(df_base):
    # Додаємо годину доби як фактор
    df_base['Hour'] = pd.to_datetime(df_base['Time']).dt.hour
    
    # Фільтруємо тільки денні години для навчання (з 6 до 20)
    df_train = df_base[(df_base['Hour'] >= 6) & (df_h['Hour'] <= 20)].copy()
    df_train = df_train.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    
    if len(df_train) < 24: # Потрібна мінімум доба чистих даних
        return None, None

    # Ознаки: Година + Погодні умови
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    X = df_train[features].fillna(0)
    
    # Ціль: Вчимося передбачати реальний Факт, використовуючи Прогноз як основну вагу
    y = df_train['Fact_MW']
    
    model = RandomForestRegressor(n_estimators=150, max_depth=10, random_state=42)
    model.fit(X, y)
    
    importance = dict(zip(features, model.feature_importances_))
    return model, importance

# --- ЛОГІКА ---
df_f, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    
    # Виправляємо назви колонок
    if 'Clouds' in df_h.columns: df_h = df_h.rename(columns={'Clouds': 'CloudCover'})
    
    # Навчання моделі
    model, importance = train_advanced_model(df_h)
    
    if df_f is not None:
        # 1. Теоретичний прогноз (базис)
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        
        if model:
            # 2. AI Корекція на основі години та погоди
            features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            
            # 3. Фізичний фільтр: вночі нуль, негативних значень не буває
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
            df_f['AI_MW'] = df_f['AI_MW'].clip(lower=0)
            model_status = "🧠 Модель: Погодинна регресія"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            model_status = "📈 Режим: Очікування даних (24г+)"
except Exception as e:
    model_status = f"⚠️ Помилка: {e}"

# --- ВІЗУАЛІЗАЦІЯ ---
st.title("☀️ SkyGrid Solar AI v17.0")
st.caption(f"Статус: {model_status} | Погода: {weather_status}")

if df_f is not None:
    t1, t2 = st.tabs(["📊 ПОГОДИННИЙ ПРОГНОЗ", "🧪 АНАЛІЗ ВПЛИВУ"])
    
    with t1:
        today_df = df_f[df_f['Time'].dt.date == now_ua.date()]
        st.metric("ПРОГНОЗ НА СЬОГОДНІ", f"{today_df['AI_MW'].sum():.1f} MWh")
        
        fig = go.Figure()
        # Теоретична крива (як могло б бути)
        fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Forecast_MW'], name="Теоретичний максимум", line=dict(dash='dot', color='rgba(255,255,255,0.3)')))
        # AI крива (реальність)
        fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['AI_MW'], name="AI Корекція (Факт)", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
        
        fig.update_layout(template="plotly_dark", height=500, margin=dict(l=0,r=0,t=20,b=0))
        st.plotly_chart(fig, use_container_width=True)

    with t2:
        if 'importance' in locals() and importance:
            c1, c2 = st.columns([1, 2])
            with c1:
                st.write("### Важливість факторів")
                imp_df = pd.DataFrame(list(importance.items()), columns=['Фактор', 'Вага']).sort_values('Вага')
                st.plotly_chart(go.Figure(go.Bar(x=imp_df['Вага'], y=imp_df['Фактор'], orientation='h', marker_color='#1f77b4')), use_container_width=True)
            with c2:
                st.info("💡 Модель тепер враховує годину доби. Це дозволяє розділяти 'ранкові' та 'денні' патерни хмарності.")

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.О. Колесник & SkyGrid AI</div>", unsafe_allow_html=True)
