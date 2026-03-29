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
                        'CloudCover': hr.get('cloudcover', 0), # Уніфіковано назву
                        'Temp': hr.get('temp', 0), 
                        'WindSpeed': hr.get('windspeed', 0), # Уніфіковано назву
                        'PrecipProb': hr.get('precipprob', 0) # Уніфіковано назву
                    })
            return pd.DataFrame(h_list), d_list, "OK"
        return None, None, f"Error: {res.status_code}"
    except Exception as e:
        return None, None, str(e)

# 3. Блок AI Моделювання
def train_solar_model(df_base):
    """Навчає Random Forest на основі історії відхилень"""
    # Очищення даних: беремо тільки там, де є факт і прогноз
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    
    # Визначаємо ознаки, на яких будемо вчитись
    features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # Перевіряємо, чи всі потрібні колонки є в наявності у файлі CSV
    available_features = [f for f in features if f in df_train.columns]
    
    if len(df_train) < 10: # Мінімальна кількість даних для старту
        return None, None

    # Заповнюємо пропуски, щоб модель не "падала"
    df_train = df_train.fillna(df_train.mean(numeric_only=True))

    X = df_train[available_features]
    y = df_train['Fact_MW']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    importance = dict(zip(available_features, model.feature_importances_))
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
        # Базовий розрахунок (без коригування)
        df_f['Raw_MW'] = df_f['Rad'] * 11.4 * 0.001
        
        # Підготовка даних для передбачення (назви мають СТРОГО збігатися з навчанням)
        X_input = df_f[['Raw_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']].copy()
        X_input.columns = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'] # Перейменування для моделі
        
        # Запуск передбачення AI
        df_f['AI_MW'] = model.predict(X_input.fillna(0))
        model_status = "ML Engine Active (Random Forest)"
    else:
        if df_f is not None:
            df_f['Raw_MW'] = df_f['Rad'] * 11.4 * 0.001
            df_f['AI_MW'] = df_f['Raw_MW'] 
        model_status = "Simple Calculation (Low Data)"

except Exception as e:
    st.error(f"Помилка бази даних: {e}")

# --- ІНТЕРФЕЙС ---
col_t, col_l = st.columns([4, 1])
with col_t:
    st.title("☀️ SkyGrid Solar AI")
    st.caption(f"Прогноз на {now_ua.strftime('%d.%m.%Y')} • {model_status}")

if df_f is not None:
    # Сума прогнозу на сьогодні
    s_ai_sum = df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
    
    t1, t2, t3 = st.tabs(["📊 АНАЛІТИКА", "🌦 МЕТЕОЦЕНТР", "🧠 ПАРАМЕТРИ AI"])

    with t1:
        c1, c2, c3 = st.columns(3)
        c1.metric("ПРОГНОЗ AI (СЬОГОДНІ)", f"{s_ai_sum:.1f} MWh")
        c2.metric("СТАТУС AI", "ACTIVE", delta="Machine Learning")
        c3.metric("МЕТЕО", "OK" if status == "OK" else "Error")

        # Основний графік
        df_p = df_f[df_f['Time'] >= pd.Timestamp(now_ua.date())].head(24)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_p['Time'], y=df_p['Raw_MW'], name="Сирий прогноз", line=dict(dash='dash', color='gray')))
        fig.add_trace(go.Scatter(x=df_p['Time'], y=df_p['AI_MW'], name="AI Коригування", fill='tozeroy', line=dict(color='#00ff7f')))
        
        fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=30,b=0))
        st.plotly_chart(fig, use_container_width=True)

        # Кнопка Excel
        excel_io = io.BytesIO()
        with pd.ExcelWriter(excel_io, engine='xlsxwriter') as writer:
            df_p.to_excel(writer, index=False)
        st.download_button("📥 Завантажити Excel", excel_io.getvalue(), "Solar_Plan.xlsx", use_container_width=True)

    with t3:
        if 'importance' in locals() and importance:
            st.subheader("Аналіз впливу метеоумов на точність")
            imp_df = pd.DataFrame(list(importance.items()), columns=['Параметр', 'Вплив']).sort_values('Вплив')
            st.plotly_chart(px.bar(imp_df, x='Вплив', y='Параметр', orientation='h', color='Вплив', template="plotly_dark"))
            st.info("Цей графік показує, які параметри погоди модель вважає найважливішими для корекції помилок.")
        else:
            st.warning("Недостатньо історичних даних для аналізу моделі.")
else:
    st.error("Помилка завантаження даних.")
