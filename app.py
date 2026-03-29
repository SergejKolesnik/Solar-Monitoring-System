import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime
import time
import pytz
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error # Для якості

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid AI v17.1: Training Analytics", layout="wide")
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
    # Додаємо годину доби
    df_base['Hour'] = pd.to_datetime(df_base['Time']).dt.hour
    
    # Фільтруємо чисті денні дані (з 6 до 20)
    df_train = df_base[(df_base['Hour'] >= 6) & (df_h['Hour'] <= 20)].copy()
    df_train = df_train.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    
    if len(df_train) < 24: # Потрібна мінімум доба
        return None, None, None

    # Ознаки
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    X = df_train[features].fillna(0)
    y = df_train['Fact_MW']
    
    model = RandomForestRegressor(n_estimators=150, max_depth=10, random_state=42)
    model.fit(X, y)
    
    # Розрахунок якості після навчання
    y_pred = model.predict(X)
    quality = mean_absolute_error(y, y_pred) # MAE (МВт)
    
    importance = dict(zip(features, model.feature_importances_))
    return model, importance, quality

# --- ЛОГІКА ---
df_f, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
daily_errors = pd.DataFrame()

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    
    # Виправляємо назви колонок
    if 'Clouds' in df_h.columns: df_h = df_h.rename(columns={'Clouds': 'CloudCover'})
    
    # Навчання та якість
    model, importance, model_quality = train_advanced_model(df_h)
    
    # ПІДГОТОВКА ГРАФІКА ПОХИБОК (ПРОЦЕС НАВЧАННЯ)
    df_h_mar = df_h[(df_h['Time'].dt.year == 2026) & (df_h['Time'].dt.month == 3)].copy()
    df_h_mar['Date'] = df_h_mar['Time'].dt.date
    # Δ MW = Факт - Базовий Прогноз (на скільки помилявся сайт)
    df_h_mar['Δ MW'] = df_h_mar['Fact_MW'] - df_h_mar['Forecast_MW']
    daily_errors = df_h_mar.groupby('Date').agg({'Δ MW':'mean'}).reset_index()

    if df_f is not None:
        # Базовий розрахунок
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        
        if model:
            # AI Корекція
            features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            
            # Фільтри
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
            df_f['AI_MW'] = df_f['AI_MW'].clip(lower=0)
            model_status = "🧠 ШІ Модель Активна"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            model_status = "📈 Очікування даних (Базовий план)"
except Exception as e:
    model_status = f"⚠️ Помилка: {e}"

# --- ВІЗУАЛІЗАЦІЯ ---
st.title("☀️ SkyGrid Solar AI v17.1")
st.caption(f"Статус: {model_status} | Погода: {weather_status}")

if df_f is not None:
    t1, t2 = st.tabs(["📊 ПРОГНОЗ ТА НАВЧАННЯ", "🧠 АНАЛІТИКА ВПЛИВУ"])
    
    with t1:
        # МЕТРИКИ ЯКОСТІ
        today_df = df_f[df_f['Time'].dt.date == now_ua.date()]
        c1, c2, c3 = st.columns(3)
        c1.metric("СЬОГОДНІ (AI)", f"{today_df['AI_MW'].sum():.1f} MWh")
        c2.metric("БАЗА ДОСВІДУ (ГОДИН)", len(df_h.dropna(subset=['Fact_MW'])))
        if 'model_quality' in locals() and model_quality:
            c3.metric("ЯКІСТЬ ШІ (MAE, МВт)", f"{model_quality:.2f}", help="Середня абсолютна помилка. Чим менше, тим краще.")

        st.markdown("---")
        
        # 1. Основний погодинний прогноз (на сьогодні)
        st.write("### Погодинний прогноз на сьогодні")
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Forecast_MW'], name="Базовий план (Теоретичний)", line=dict(dash='dot', color='rgba(255,255,255,0.3)')))
        fig_h.add_trace(go.Scatter(x=df_f['Time'], y=df_f['AI_MW'], name="AI Корекція (Реальний Факт)", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
        fig_h.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=10,b=0), legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig_h, use_container_width=True)

        # 2. НОВИЙ ГРАФІК: ПРОЦЕС НАВЧАННЯ (ПОХИБКИ БАЗИ)
        st.markdown("---")
        if not daily_errors.empty:
            st.write("### Аналіз процесу навчання (Середня похибка Δ за добу)")
            st.caption("ШІ вчиться на основі цих похибок. Коли лінія наближається до нуля, якість прогнозу сайту покращується.")
            fig_e = go.Figure()
            # Додаємо лінію Факт-План
            fig_e.add_trace(go.Scatter(x=daily_errors['Date'], y=daily_errors['Δ MW'], name="Δ (Факт - План)", line=dict(color='#ff4b4b', width=3)))
            # Додаємо нульову лінію
            fig_e.add_trace(go.Scatter(x=daily_errors['Date'], y=[0]*len(daily_errors), name="Ідеальний Прогноз", line=dict(color='white', width=1, dash='dash'), opacity=0.5))
            
            fig_e.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=10,b=0), legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_e, use_container_width=True)

    with t2:
        if 'importance' in locals() and importance:
            st.write("### Важливість погодних факторів")
            imp_df = pd.DataFrame(list(importance.items()), columns=['Фактор', 'Вага']).sort_values('Вага')
            st.plotly_chart(go.Figure(go.Bar(x=imp_df['Вага'], y=imp_df['Фактор'], orientation='h', marker_color='#1f77b4')), use_container_width=True)
            st.info("💡 Модель тепер враховує годину доби, що дозволяє розділяти 'ранкові' та 'денні' патерни.")

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.О. Колесник & SkyGrid AI</div>", unsafe_allow_html=True)
