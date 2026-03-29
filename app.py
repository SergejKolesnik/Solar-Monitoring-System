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
from sklearn.ensemble import RandomForestRegressor  # AI Модель

# 1. Конфігурація сторінки
st.set_page_config(page_title="SkyGrid Solar AI v16.0", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. Функція отримання погоди
@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
    except:
        return None, None, "Missing API Key"

    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,tempmax,tempmin,cloudcover,solarradiation,windspeed,winddir,precipprob,conditions,icon&key={api_key}&contentType=json"
    
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list, d_list = [], []
            for d in data['days']:
                d_list.append({
                    'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'), 
                    'Макс': d.get('tempmax'), 'Мін': d.get('tempmin'), 
                    'Опади': d.get('precipprob'), 'Вітер': d.get('windspeed'), 
                    'Умови': d.get('conditions'), 'Icon': d.get('icon')
                })
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"), 
                        'Rad': hr.get('solarradiation', 0), 
                        'Clouds': hr.get('cloudcover', 0), 
                        'Temp': hr.get('temp', 0), 
                        'WindSpd': hr.get('windspeed', 0),
                        'Precip': hr.get('precipprob', 0)
                    })
            return pd.DataFrame(h_list), d_list, "OK"
        return None, None, f"Error: {res.status_code}"
    except Exception as e:
        return None, None, str(e)

# 3. Блок AI Моделювання
def train_solar_model(df_base):
    """Навчає Random Forest на основі історії відхилень"""
    # Очищення даних
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    
    # Спроба знайти потрібні колонки (гнучкий пошук назв)
    mapping = {
        'CloudCover': ['CloudCover', 'Clouds', 'cloudcover'],
        'Temp': ['Temp', 'temp', 'Temperature'],
        'WindSpeed': ['WindSpeed', 'WindSpd', 'windspeed'],
        'PrecipProb': ['PrecipProb', 'precipprob', 'Precip']
    }
    
    features = ['Forecast_MW']
    for feat, variants in mapping.items():
        for v in variants:
            if v in df_train.columns:
                df_train[feat] = df_train[v]
                features.append(feat)
                break
    
    if len(df_train) < 15: # Мінімум 15 годин історії для навчання
        return None, None

    # Заповнюємо пропуски середнім, щоб модель не видавала помилку
    df_train = df_train.fillna(df_train.mean(numeric_only=True))

    X = df_train[features]
    y = df_train['Fact_MW']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    importance = dict(zip(features, model.feature_importances_))
    return model, importance

# --- ЛОГІКА ЗАВАНТАЖЕННЯ ---
df_f, day_forecast, status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
model_status = "Ініціалізація..."

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    df_h['Time'] = pd.to_datetime(df_h['Time'])
    
    # Навчання AI
    model, importance = train_solar_model(df_h)
    
    if model and df_f is not None:
        # Підготовка даних для прогнозу
        df_f['Raw_MW'] = df_f['Rad'] * 11.4 * 0.001
        
        # Створюємо вхідний масив для моделі з тими ж колонками, на яких вчили
        # Мапимо колонки прогнозу погоди на колонки моделі
        X_input = pd.DataFrame({
            'Forecast_MW': df_f['Raw_MW'],
            'CloudCover': df_f['Clouds'],
            'Temp': df_f['Temp'],
            'WindSpeed': df_f['WindSpd'],
            'PrecipProb': df_f['Precip']
        })
        
        df_f['AI_MW'] = model.predict(X_input.fillna(0))
        model_status = "ML Engine Active (Random Forest)"
    else:
        df_f['Raw_MW'] = df_f['Rad'] * 11.4 * 0.001
        df_f['AI_MW'] = df_f['Raw_MW'] # Fallback
        model_status = "Simple Calculation (Low Data)"

except Exception as e:
    st.error(f"Помилка бази даних: {e}")

# --- ІНТЕРФЕЙС ---
col_t, col_l = st.columns([4, 1])
with col_t:
    st.title("☀️ SkyGrid Solar AI")
    st.caption(f"Прогноз на {now_ua.strftime('%d.%m.%Y')} • {model_status}")

if df_f is not None:
    s_ai_sum = df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
    
    t1, t2, t3 = st.tabs(["📊 АНАЛІТИКА", "🌦 МЕТЕОЦЕНТР", "🧠 ПАРАМЕТРИ AI"])

    with t1:
        c1, c2, c3 = st.columns(3)
        c1.metric("ПРОГНОЗ AI (СЬОГОДНІ)", f"{s_ai_sum:.1f} MWh")
        c2.metric("СТАТУС AI", "ACTIVE", delta="Machine Learning")
        c3.metric("МЕТЕО", "OK" if status == "OK" else "Error")

        # Графік прогнозу
        df_p = df_f[df_f['Time'] >= pd.Timestamp(now_ua.date())].head(24)
        fig = px.area(df_p, x='Time', y='AI_MW', title="Погодинний прогноз генерації (AI Коригування)",
                      color_discrete_sequence=['#00ff7f'])
        st.plotly_chart(fig, use_container_width=True)

        # Кнопка Excel
        excel_io = io.BytesIO()
        with pd.ExcelWriter(excel_io, engine='xlsxwriter') as writer:
            df_p[['Time', 'AI_MW', 'Raw_MW', 'Clouds', 'Temp']].to_excel(writer, index=False)
        st.download_button("📥 Завантажити План (Excel)", excel_io.getvalue(), "Solar_Plan.xlsx", use_container_width=True)

    with t3:
        if 'importance' in locals() and importance:
            st.subheader("Аналіз впливу метеоумов на точність")
            imp_df = pd.DataFrame(list(importance.items()), columns=['Параметр', 'Вплив']).sort_values('Вплив')
            st.plotly_chart(px.bar(imp_df, x='Вплив', y='Параметр', orientation='h', color='Вплив'))
            st.info("Цей графік показує, які параметри погоди модель вважає найважливішими для корекції помилок.")
        else:
            st.warning("Недостатньо історичних даних для аналізу моделі.")
else:
    st.error("Помилка завантаження даних погоди.")
