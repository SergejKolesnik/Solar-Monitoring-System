import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime, timedelta
import time
import pytz
import io
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI v18.5", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def fetch_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,tempmax,tempmin,cloudcover,solarradiation,windspeed,winddir,precipprob,conditions,icon&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list, d_list = [], []
            for d in data['days']:
                d_list.append({
                    'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'),
                    'Макс': d.get('tempmax'),
                    'Вітер': d.get('windspeed'),
                    'Icon': d.get('icon', 'clear-day'),
                    'Умови': d.get('conditions'),
                    'Мін': d.get('tempmin'),
                    'Опади': d.get('precipprob')
                })
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
            return pd.DataFrame(h_list), d_list, "OK"
    except: pass
    return None, None, "API Error"

def train_solar_engine(df_base):
    df_base['Time'] = pd.to_datetime(df_base['Time'])
    df_base['Hour'] = df_base['Time'].dt.hour
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    if len(df_train) < 24: return None, None, len(df_train), 0
    
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    X = df_train[features].fillna(0)
    y = df_train['Fact_MW']
    
    model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    model.fit(X, y)
    
    # Розрахунок точності (R2 score)
    y_pred = model.predict(X)
    accuracy = r2_score(y, y_pred) * 100
    
    return model, df_train, len(df_train), accuracy

# --- ПІДГОТОВКА ДАНИХ ---
df_f, day_forecast, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    if 'Clouds' in df_h.columns: df_h = df_h.rename(columns={'Clouds': 'CloudCover'})
    model, df_trained_data, data_count, model_acc = train_solar_engine(df_h)
    
    if df_f is not None:
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        if model:
            features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
            df_f['AI_MW'] = df_f['AI_MW'].clip(lower=0)
            model_status = f"✅ Модель навчена ({data_count} год)"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            model_status = f"⏳ Накопичення даних..."
except: 
    model_status = "⚠️ База недоступна"
    data_count, model_acc = 0, 0

# --- ІНТЕРФЕЙС ---
st.title("☀️ SkyGrid Solar AI v18.5")
st.caption(f"С.І. Колесник • Нікополь • {now_ua.strftime('%d.%m.%Y %H:%M')}")

t1, t2, t3, t4 = st.tabs(["📊 ПРОГНОЗ 3 ДНІ", "🌦 МЕТЕОЦЕНТР", "🧠 МОНІТОР НАВЧАННЯ", "📑 БАЗА"])

with t1:
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2])
    days_list = [now_ua.date(), (now_ua + timedelta(days=1)).date(), (now_ua + timedelta(days=2)).date()]
    labels = ["СЬОГОДНІ", "ЗАВТРА", "ПІСЛЯЗАВТРА"]
    
    @st.dialog("Погодинна деталізація")
    def show_details(day_date, data):
        st.write(f"### Прогноз на {day_date.strftime('%d.%m.%Y')}")
        df_day = data[data['Time'].dt.date == day_date].copy()
        df_day['Година'] = df_day['Time'].dt.strftime('%H:00')
        st.table(df_day[['Година', 'AI_MW', 'Forecast_MW']].rename(columns={'AI_MW': 'План ШІ (МВт)', 'Forecast_MW': 'Сайт (МВт)'}))

    for i, col in enumerate([c1, c2, c3]):
        d_data = df_f[df_f['Time'].dt.date == days_list[i]]
        with col:
            st.info(f"📅 {labels[i]} ({days_list[i].strftime('%d.%m')})")
            st.metric("План AI", f"{d_data['AI_MW'].sum():.1f} MWh")
            st.metric("Сайт", f"{d_data['Forecast_MW'].sum():.1f} MWh")
            if st.button(f"👁️ Детально", key=f"btn_{i}"):
                show_details(days_list[i], df_f)

    with c4:
        st.write("**Статус ШІ:**", model_status)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_f.head(72)[['Time', 'AI_MW', 'Forecast_MW']].to_excel(writer, index=False)
        st.download_button("📥 EXCEL ПЛАН (72 год)", output.getvalue(), f"Solar_Plan_v18.5.xlsx", use_container_width=True)

    fig_main = go.Figure()
    fig_main.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), name="Теорія (Сайт)", line=dict(dash='dot', color='gray')))
    fig_main.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['AI_MW'].head(72), name="План AI", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    fig_main.update_layout(template="plotly_dark", height=350, margin=dict(l=0,r=0,t=10,b=0), legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    st.plotly_chart(fig_main, use_container_width=True)

with t2:
    if day_forecast:
        st.subheader("Прогноз погоди по Нікополю")
        def get_icon(name):
            icons = {"rain": "🌧️", "cloudy": "☁️", "partly-cloudy-day": "⛅", "clear-day": "☀️", "wind": "💨", "snow": "❄️"}
            return icons.get(name, "🌡️")
        
        f_cols = st.columns(len(day_forecast))
        for i, d in enumerate(day_forecast):
            with f_cols[i]:
                bg = "rgba(255, 75, 75, 0.1)" if d['Вітер'] > 12 else "rgba(255, 255, 255, 0.05)"
                st.markdown(f"""
                <div style='background:{bg}; padding:10px; border-radius:10px; text-align:center; border:1px solid rgba(255,255,255,0.1);'>
                    <p style='margin:0; font-size:11px; color:gray;'>{d['Дата']}</p>
                    <p style='margin:5px 0; font-size:22px;'>{get_icon(d['Icon'])}</p>
                    <p style='margin:0; font-weight:bold;'>{d['Макс']:.0f}°</p>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.info("ℹ️ Дані надано сервісом [Visual Crossing Weather](https://www.visualcrossing.com/weather-data)")

with t3:
    st.subheader("🧠 Стан нейронної мережі")
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Обсяг знань", f"{data_count} год", help="Кількість годин з історичними даними в базі")
    with m2:
        st.metric("Глибина досвіду", f"{data_count/24:.1f} днів", help="Скільки повних діб ШІ аналізував ситуацію")
    with m3:
        st.metric("Точність навчання", f"{model_acc:.1f}%", help="Коефіцієнт відповідності моделі реальним даним (R2)")
    
    st.write("**Прогрес формування інтелекту:**")
    progress = min(data_count / 500, 1.0) # 500 годин як еталон первинного навчання
    st.progress(progress)
    
    st.write("---")
    if 'df_h' in locals() and not df_h.empty:
        # Стовпчики 7 днів
        daily_stats = df_h.groupby(pd.to_datetime(df_h['Time']).dt.date).agg({'Forecast_MW': 'sum', 'Fact_MW': 'sum'}).tail(7).reset_index()
        fig_battle = go.Figure()
        fig_battle.add_trace(go.Bar(x=daily_stats['Time'], y=daily_stats['Forecast_MW'], name="Сайт", marker_color='orange'))
        fig_battle.add_trace(go.Bar(x=daily_stats['Time'], y=daily_stats['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f'))
        fig_battle.update_layout(template="plotly_dark", barmode='group', height=350, title="Порівняння Сайт vs Факт (7 днів)")
        st.plotly_chart(fig_battle, use_container_width=True)

with t4:
    if 'df_h' in locals():
        st.write("### Останні 20 записів бази")
        st.dataframe(df_h.tail(20), use_container_width=True)

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.І. Колесник & SkyGrid AI • 2026</div>", unsafe_allow_html=True)
