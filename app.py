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
st.set_page_config(page_title="SkyGrid Solar AI v18.7", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# СТИЛІЗАЦІЯ ДЛЯ М'ЯКОГО РЕЖИМУ (БЕЗ ВИДАЛЕННЯ ФУНКЦІЙ)
st.markdown("""
    <style>
    .stApp {
        background-color: #f0f2f6; /* М'який сіро-блакитний фон */
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02);
    }
    div[data-testid="stExpander"] {
        background-color: #ffffff;
        border-radius: 12px;
    }
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

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
                    'Мін': d.get('tempmin'),
                    'Опади': d.get('precipprob'),
                    'Вітер': d.get('windspeed'),
                    'Умови': d.get('conditions'),
                    'Icon': d.get('icon', 'clear-day')
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
            model_status = f"✅ Модель активна ({data_count} год)"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            model_status = f"⏳ Навчання... ({data_count}/24)"
except: 
    model_status = "⚠️ Помилка бази"
    data_count, model_acc = 0, 0

# --- ІНТЕРФЕЙС ---
st.title("☀️ SkyGrid Solar AI v18.7")
st.caption(f"С.І. Колесник • Нікополь • {now_ua.strftime('%d.%m.%Y %H:%M')}")

t1, t2, t3, t4 = st.tabs(["📊 ПРОГНОЗ 3 ДНІ", "🌦 МЕТЕОЦЕНТР", "🧠 МОНІТОР НАВЧАННЯ", "📑 БАЗА"])

with t1:
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2])
    days_list = [now_ua.date(), (now_ua + timedelta(days=1)).date(), (now_ua + timedelta(days=2)).date()]
    labels = ["СЬОГОДНІ", "ЗАВТРА", "ПІСЛЯЗАВТРА"]
    
    @st.dialog("Детальний прогноз")
    def show_details(day_date, data):
        st.write(f"### Погодинний план на {day_date.strftime('%d.%m')}")
        df_day = data[data['Time'].dt.date == day_date].copy()
        df_day['Година'] = df_day['Time'].dt.strftime('%H:00')
        st.dataframe(df_day[['Година', 'AI_MW', 'Forecast_MW']].rename(columns={'AI_MW': 'ШІ (МВт)', 'Forecast_MW': 'Сайт (МВт)'}), use_container_width=True, hide_index=True)

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
        st.download_button("📥 EXCEL ПЛАН (72 год)", output.getvalue(), f"Solar_Plan.xlsx", use_container_width=True)

    fig_main = go.Figure()
    fig_main.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), name="Сайт", line=dict(dash='dot', color='#adb5bd')))
    fig_main.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['AI_MW'].head(72), name="План ШІ", fill='tozeroy', line=dict(color='#74c69d', width=3)))
    fig_main.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350, font=dict(color='#444'), margin=dict(l=0,r=0,t=10,b=0), legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    st.plotly_chart(fig_main, use_container_width=True)

with t2:
    if day_forecast:
        st.subheader("Прогноз по Нікополю")
        def get_icon(name):
            icons = {"rain": "🌧️", "cloudy": "☁️", "partly-cloudy-day": "⛅", "clear-day": "☀️", "wind": "💨", "snow": "❄️"}
            return icons.get(name, "🌡️")
        
        f_cols = st.columns(len(day_forecast))
        for i, d in enumerate(day_forecast):
            with f_cols[i]:
                bg = "rgba(255, 107, 107, 0.1)" if d['Вітер'] > 12 else "white"
                st.markdown(f"""
                <div style='background:{bg}; padding:10px; border-radius:10px; text-align:center; border:1px solid #dee2e6;'>
                    <p style='margin:0; font-size:11px; color:#6c757d;'>{d['Дата']}</p>
                    <p style='margin:5px 0; font-size:22px;'>{get_icon(d['Icon'])}</p>
                    <p style='margin:0; font-weight:bold; color:#495057;'>{d['Макс']:.0f}°</p>
                </div>
                """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(day_forecast)[['Дата', 'Умови', 'Мін', 'Макс', 'Опади', 'Вітер']], hide_index=True, use_container_width=True)

with t3:
    st.subheader("🧠 Стан нейронної мережі")
    m1, m2, m3 = st.columns(3)
    m1.metric("База знань", f"{data_count} год")
    m2.metric("Досвід", f"{data_count/24:.1f} дн")
    m3.metric("Точність R2", f"{model_acc:.1f}%")
    
    st.write("**Прогрес навчання (зрілість бази):**")
    progress_val = min(data_count / 500, 1.0)
    st.markdown(f"""
        <div style="width: 100%; background-color: #e9ecef; border-radius: 10px; height: 25px;">
            <div style="width: {progress_val*100}%; background-color: #74c69d; height: 100%; border-radius: 10px;"></div>
        </div>
    """, unsafe_allow_html=True)
    
    st.write("---")
    if 'df_h' in locals() and not df_h.empty:
        st.subheader("📊 Сайт vs План ШІ vs Факт АСКОЕ (7 днів)")
        hist_data = df_h.copy()
        if model:
            feats = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            hist_data['AI_MW'] = model.predict(hist_data[feats].fillna(0))
            hist_data.loc[(hist_data['Hour'] < 5) | (hist_data['Hour'] > 20), 'AI_MW'] = 0
        
        daily_perf = hist_data.groupby(hist_data['Time'].dt.date).agg({'Forecast_MW':'sum', 'AI_MW':'sum', 'Fact_MW':'sum'}).tail(7).reset_index()
        fig_b = go.Figure()
        fig_b.add_trace(go.Bar(x=daily_perf['Time'], y=daily_perf['Forecast_MW'], name="Сайт", marker_color='#ffc300'))
        fig_b.add_trace(go.Bar(x=daily_perf['Time'], y=daily_perf['AI_MW'], name="ШІ", marker_color='#4ea8de'))
        fig_b.add_trace(go.Bar(x=daily_perf['Time'], y=daily_perf['Fact_MW'], name="Факт", marker_color='#74c69d'))
        fig_b.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', barmode='group', height=350, font=dict(color='#444'))
        st.plotly_chart(fig_b, use_container_width=True)

        st.write("### Теплова карта похибок Δ (Факт - План)")
        df_heat = df_h.tail(168).copy()
        df_heat['Error'] = df_heat['Fact_MW'] - df_heat['Forecast_MW']
        df_heat['Дата'] = df_heat['Time'].dt.strftime('%d.%m')
        pivot = df_heat[df_heat['Hour'].between(7,19)].pivot(index='Дата', columns='Hour', values='Error')
        fig_hm = px.imshow(pivot, color_continuous_scale="RdBu_r")
        fig_hm.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=350)
        st.plotly_chart(fig_hm, use_container_width=True)

st.markdown("---")
st.markdown("<div style='text-align:center; color:#999; font-size:12px;'><b>Розробка:</b> С.І. Колесник & SkyGrid AI • 2026</div>", unsafe_allow_html=True)
