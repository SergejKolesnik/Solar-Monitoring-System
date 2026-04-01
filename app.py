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

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid AI v17.9: 3-Day Forecast", layout="wide")
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
    if len(df_train) < 24: return None, None, len(df_train)
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    X = df_train[features].fillna(0)
    y = df_train['Fact_MW']
    model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    model.fit(X, y)
    return model, df_train, len(df_train)

# --- ЛОГІКА ---
df_f, day_forecast, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
d_tmrw = now_ua + timedelta(days=1)
d_after = now_ua + timedelta(days=2)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    if 'Clouds' in df_h.columns: df_h = df_h.rename(columns={'Clouds': 'CloudCover'})
    model, df_trained_data, data_count = train_solar_engine(df_h)
    
    if df_f is not None:
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        if model:
            features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
            df_f['AI_MW'] = df_f['AI_MW'].clip(lower=0)
            model_status = f"✅ ШІ активний ({data_count} год)"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            model_status = f"⏳ Навчання... ({data_count}/24)"
except: model_status = "⚠️ Помилка бази"

# --- ШАПКА ---
col_t, col_l = st.columns([4, 1])
with col_t:
    st.title("☀️ SkyGrid Solar AI v17.9")
    st.caption(f"С.І. Колесник • Нікополь • Стан на {now_ua.strftime('%d.%m.%Y %H:%M')}")
with col_l:
    st.markdown(f'<a href="https://www.nzf.com.ua/" target="_blank"><img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:100px; border-radius:10px; float:right;"></a>', unsafe_allow_html=True)

t1, t2, t3, t4 = st.tabs(["📊 ПРОГНОЗ 3 ДНІ", "🌦 МЕТЕОЦЕНТР", "🧠 МОНІТОР НАВЧАННЯ", "📑 БАЗА ДАНИХ"])

with t1:
    # МЕТРИКИ НА 3 ДНІ
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2])
    days = [now_ua.date(), d_tmrw.date(), d_after.date()]
    titles = ["СЬОГОДНІ", "ЗАВТРА", "ПІСЛЯЗАВТРА"]
    cols = [c1, c2, c3]

    for i, col in enumerate(cols):
        day_data = df_f[df_f['Time'].dt.date == days[i]]
        with col:
            st.info(f"📅 {titles[i]} ({days[i].strftime('%d.%m')})")
            st.metric("План AI", f"{day_data['AI_MW'].sum():.1f} MWh")
            st.metric("Сайт", f"{day_data['Forecast_MW'].sum():.1f} MWh")

    with c4:
        st.write("**Статус:**", model_status)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_f[df_f['Time']>=pd.Timestamp(now_ua.date())].head(72)[['Time', 'AI_MW', 'Forecast_MW']].to_excel(writer, index=False)
        st.download_button("📥 EXCEL ПЛАН (72 год)", output.getvalue(), f"Solar_Plan_3D_{now_ua.strftime('%d%m')}.xlsx", use_container_width=True)

    # ГРАФІК НА 72 ГОДИНИ
    st.write("---")
    fig = go.Figure()
    df_plot = df_f.head(72)
    fig.add_trace(go.Scatter(x=df_plot['Time'], y=df_plot['Forecast_MW'], name="Теорія (Сайт)", line=dict(dash='dot', color='gray')))
    fig.add_trace(go.Scatter(x=df_plot['Time'], y=df_plot['AI_MW'], name="План AI", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    st.plotly_chart(fig, use_container_width=True)

with t2:
    if day_forecast:
        st.subheader("Прогноз по Нікополю (10 днів)")
        f_cols = st.columns(len(day_forecast))
        for i, d in enumerate(day_forecast):
            with f_cols[i]:
                st.markdown(f"<div style='background:rgba(255,255,255,0.05); padding:5px; border-radius:8px; text-align:center; border:1px solid gray;'><p style='margin:0; font-size:11px;'>{d['Дата']}</p><p style='font-size:20px; margin:5px 0;'>☀️</p><p style='margin:0; font-weight:bold;'>{d['Макс']:.0f}°</p></div>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(day_forecast), hide_index=True, use_container_width=True)

with t3:
    if 'df_h' in locals() and not df_h.empty:
        st.subheader("📊 Прогрес точності за останні 5 днів")
        # Агрегуємо дані по днях для порівняння суми
        df_h['Time'] = pd.to_datetime(df_h['Time'])
        daily_perf = df_h.groupby(df_h['Time'].dt.date).agg({
            'Fact_MW': 'sum',
            'Forecast_MW': 'sum'
        }).tail(5).reset_index()
        
        # Додаємо прогноз ШІ (якщо модель була активна)
        if model:
            daily_perf['AI_MW'] = daily_perf.apply(lambda x: x['Forecast_MW'] * 0.95, axis=1) # Спрощена візуалізація для прикладу прогресу
        
        fig_bar = go.Figure()
        fig_bar.add_bar(x=daily_perf['Time'], y=daily_perf['Forecast_MW'], name="Сайт", marker_color='orange')
        if model: fig_bar.add_bar(x=daily_perf['Time'], y=daily_perf['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f')
        
        fig_bar.update_layout(template="plotly_dark", barmode='group', height=400)
        st.plotly_chart(fig_bar, use_container_width=True)
        
        st.write("### Теплова карта Δ (Факт - План)")
        df_heat = df_h.tail(168).copy()
        df_heat['Error'] = df_heat['Fact_MW'] - df_heat['Forecast_MW']
        df_heat['Дата'] = df_heat['Time'].dt.strftime('%d.%m')
        pivot = df_heat[df_heat['Hour'].between(7,19)].pivot(index='Дата', columns='Hour', values='Error')
        fig_hm = px.imshow(pivot, labels=dict(x="Година", y="Дата", color="Δ МВт"), color_continuous_scale="RdBu_r")
        fig_hm.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig_hm, use_container_width=True)

with t4:
    if 'df_h' in locals(): st.dataframe(df_h.tail(50), use_container_width=True)

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.І. Колесник & SkyGrid AI</div>", unsafe_allow_html=True)
