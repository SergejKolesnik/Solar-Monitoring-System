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

# Спроба імпорту моделі
try:
    from sklearn.ensemble import RandomForestRegressor
    SKLEARN_READY = True
except ImportError:
    SKLEARN_READY = False

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI v16.4", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob,conditions,icon&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': hr.get('solarradiation', 0),
                        'CloudCover': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0),
                        'WindSpeed': hr.get('windspeed', 0),
                        'PrecipProb': hr.get('precipprob', 0)
                    })
            return pd.DataFrame(h_list), "OK"
    except: pass
    return None, "Помилка API"

def train_solar_model(df_base):
    if not SKLEARN_READY: return None, None, []
    # Ознаки для навчання
    features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    
    # Вибираємо тільки ті колонки, що є в наявності
    actual_features = [f for f in features if f in df_train.columns]
    
    if len(df_train) < 15: # Мінімум 15 годин досвіду для першого запуску
        return None, None, []

    X = df_train[actual_features].fillna(0)
    y = df_train['Fact_MW']
    
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    importance = dict(zip(actual_features, model.feature_importances_))
    return model, importance, actual_features

# --- ОСНОВНА ЛОГІКА ---
df_f, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
model_status = "Очікування даних..."

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    
    # Виправляємо назви колонок якщо треба
    if 'Clouds' in df_h.columns: df_h = df_h.rename(columns={'Clouds': 'CloudCover'})
    
    model, importance, model_features = train_solar_model(df_h)
    
    if df_f is not None:
        # Базовий розрахунок (11.4 МВт потужність станції)
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        
        if model:
            X_input = df_f[model_features].fillna(0)
            df_f['AI_MW'] = model.predict(X_input)
            model_status = "🤖 AI Модель Активна"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW'] # План Б
            model_status = "📈 Накопичення бази (Базовий план)"
except Exception as e:
    model_status = f"⚠️ Помилка: {str(e)}"

# --- ВІЗУАЛІЗАЦІЯ ---
st.title("☀️ SkyGrid Solar AI v16.4")
st.caption(f"Статус: {model_status} | Погода: {weather_status}")

if df_f is not None:
    t1, t2 = st.tabs(["📊 ГРАФІК ПРОГНОЗУ", "🧠 АНАЛІТИКА"])
    
    with t1:
        today_df = df_f[df_f['Time'].dt.date == now_ua.date()]
        st.metric("ПРОГНОЗ НА СЬОГОДНІ", f"{today_df['AI_MW'].sum():.1f} MWh")
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Forecast_MW'], name="Базовий план (Сайт)", line=dict(dash='dash', color='gray')))
        fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['AI_MW'], name="AI Корекція", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
        
        fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)

    with t2:
        if 'importance' in locals() and importance:
            st.subheader("Вплив погодних факторів")
            imp_df = pd.DataFrame(list(importance.items()), columns=['Фактор', 'Вага']).sort_values('Вага')
            st.plotly_chart(px.bar(imp_df, x='Вага', y='Фактор', orientation='h', color_discrete_sequence=['#1f77b4']))
        else:
            st.info("📊 Аналіз факторів буде доступний після накопичення 15 годин фактичних даних у файлі solar_ai_base.csv")

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.О. Колесник & SkyGrid AI</div>", unsafe_allow_html=True)
