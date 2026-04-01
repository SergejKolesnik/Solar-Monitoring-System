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
st.set_page_config(page_title="SkyGrid AI v17.8", layout="wide")
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
    if len(df_train) < 20: return None, None, len(df_train)
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    X = df_train[features].fillna(0)
    y = df_train['Fact_MW']
    model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    model.fit(X, y)
    importance = dict(zip(features, model.feature_importances_))
    return model, importance, len(df_train)

# --- ЛОГІКА ---
df_f, day_forecast, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
tomorrow_ua = now_ua + timedelta(days=1)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    if 'Clouds' in df_h.columns: df_h = df_h.rename(columns={'Clouds': 'CloudCover'})
    model, importance, data_count = train_solar_engine(df_h)
    
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
            model_status = f"⏳ Навчання... ({data_count}/20)"
except: model_status = "⚠️ Помилка бази"

# --- ШАПКА ---
col_t, col_l = st.columns([4, 1])
with col_t:
    st.title("☀️ SkyGrid Solar AI v17.8")
    st.caption(f"Локація: Нікополь • NZF • Стан на {now_ua.strftime('%d.%m.%Y %H:%M')}")
with col_l:
    st.markdown(f'<a href="https://www.nzf.com.ua/" target="_blank"><img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:100px; border-radius:10px; float:right;"></a>', unsafe_allow_html=True)

t1, t2, t3, t4 = st.tabs(["📊 ПРОГНОЗ", "🌦 МЕТЕОЦЕНТР", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with t1:
    today_df = df_f[df_f['Time'].dt.date == now_ua.date()]
    tmrw_df = df_f[df_f['Time'].dt.date == tomorrow_ua.date()]
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info(f"📅 СЬОГОДНІ ({now_ua.strftime('%d.%m')})")
        st.metric("План AI", f"{today_df['AI_MW'].sum():.1f} MWh")
        st.metric("Сайт", f"{today_df['Forecast_MW'].sum():.1f} MWh")
    with c2:
        st.success(f"📅 ЗАВТРА ({tomorrow_ua.strftime('%d.%m')})")
        st.metric("План AI", f"{tmrw_df['AI_MW'].sum():.1f} MWh")
        st.metric("Сайт", f"{tmrw_df['Forecast_MW'].sum():.1f} MWh")
    with c3:
        st.write("**Статус:**", model_status)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_f[df_f['Time']>=pd.Timestamp(now_ua.date())].head(48)[['Time', 'AI_MW', 'Forecast_MW']].to_excel(writer, index=False)
        st.download_button("📥 EXCEL ПЛАН (48 год)", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d%m')}.xlsx", use_container_width=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_f['Time'].head(48), y=df_f['Forecast_MW'].head(48), name="Теорія (Сайт)", line=dict(dash='dot', color='gray')))
    fig.add_trace(go.Scatter(x=df_f['Time'].head(48), y=df_f['AI_MW'].head(48), name="План AI", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=20,b=0), legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
    st.plotly_chart(fig, use_container_width=True)

with t2:
    if day_forecast:
        cols = st.columns(len(day_forecast))
        for i, d in enumerate(day_forecast):
            with cols[i]:
                bg = "rgba(255, 75, 75, 0.15)" if d['Вітер'] > 12 else "rgba(255, 255, 255, 0.05)"
                st.markdown(f"<div style='background:{bg}; padding:10px; border-radius:12px; text-align:center; border:1px solid rgba(255,255,255,0.1);'><p style='margin:0; font-size:12px;'>{d['Дата']}</p><p style='font-size:25px;'>☀️</p><p style='margin:0; font-weight:bold;'>{d['Макс']:.0f}°</p></div>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(day_forecast), hide_index=True)

with t3:
    if 'df_h' in locals() and not df_h.empty:
        st.write("### Теплова карта похибок (Δ МВт)")
        df_heat = df_h.copy()
        df_heat['Error'] = df_heat['Fact_MW'] - df_heat['Forecast_MW']
        df_heat['Дата'] = df_heat['Time'].dt.strftime('%d.%m')
        pivot = df_heat[df_heat['Hour'].between(7,19)].pivot(index='Дата', columns='Hour', values='Error')
        fig_hm = px.imshow(pivot, labels=dict(x="Година", y="Дата", color="Δ МВт"), color_continuous_scale="RdBu_r")
        fig_hm.update_layout(template="plotly_dark", height=450)
        st.plotly_chart(fig_hm, use_container_width=True)

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.І. Колесник & SkyGrid AI</div>", unsafe_allow_html=True)
