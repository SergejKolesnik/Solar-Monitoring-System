import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from datetime import datetime
import time
import pytz
import io
from sklearn.ensemble import RandomForestRegressor

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid AI v17.5: Hourly Ratios", layout="wide")
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
            df = pd.DataFrame(h_list)
            return df, d_list, "OK"
    except: pass
    return None, None, "API Error"

def train_solar_engine(df_base):
    df_base['Time'] = pd.to_datetime(df_base['Time'])
    df_base['Hour'] = df_base['Time'].dt.hour
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    if len(df_train) < 20: return None, len(df_train)
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    X = df_train[features].fillna(0)
    y = df_train['Fact_MW']
    model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    model.fit(X, y)
    return model, len(df_train)

# --- ЛОГІКА ЗАВАНТАЖЕННЯ ---
df_f, day_forecast, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    if 'Clouds' in df_h.columns: df_h = df_h.rename(columns={'Clouds': 'CloudCover'})
    model, data_count = train_solar_engine(df_h)
    
    if df_f is not None:
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        if model:
            features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
            df_f['AI_MW'] = df_f['AI_MW'].clip(lower=0)
            
            # Розрахунок погодинного коефіцієнта (AI_MW / Forecast_MW)
            df_f['AI_Ratio'] = (df_f['AI_MW'] / df_f['Forecast_MW']).fillna(0).replace([np.inf, -np.inf], 0)
            df_f.loc[df_f['Forecast_MW'] < 0.05, 'AI_Ratio'] = 0
            
            model_status = f"✅ ШІ активний (База: {data_count} год)"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            df_f['AI_Ratio'] = 1.0
            model_status = f"⏳ Навчання... ({data_count}/20 год)"
except: model_status = "⚠️ Помилка бази"

# --- ШАПКА ---
col_t, col_l = st.columns([4, 1])
with col_t:
    st.title("☀️ SkyGrid Solar AI v17.5")
    st.caption(f"Нікополь • NZF • Стан на {now_ua.strftime('%d.%m.%Y %H:%M')}")
with col_l:
    st.markdown(f'<a href="https://www.nzf.com.ua/main.aspx" target="_blank"><img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:100px; border-radius:10px; float:right;"></a>', unsafe_allow_html=True)

t1, t2, t3, t4 = st.tabs(["📊 ПРОГНОЗ ТА КОЕФІЦІЄНТИ", "🌦 МЕТЕОЦЕНТР", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with t1:
    today_df = df_f[df_f['Time'].dt.date == now_ua.date()]
    c1, c2, c3 = st.columns(3)
    c1.metric("ПРОГНОЗ AI (СЬОГОДНІ)", f"{today_df['AI_MW'].sum():.1f} MWh")
    c2.metric("СЕРЕДНІЙ КОЕФІЦІЄНТ", f"{today_df[today_df['AI_Ratio']>0]['AI_Ratio'].mean():.2f}x")
    c3.metric("СТАТУС МОДЕЛІ", model_status)

    # КНОПКА EXCEL
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_f[df_f['Time']>=pd.Timestamp(now_ua.date())].head(72)[['Time', 'AI_MW', 'Forecast_MW', 'AI_Ratio']].rename(columns={'AI_MW':'План AI', 'Forecast_MW':'Теорія', 'AI_Ratio':'Коефіцієнт'}).to_excel(writer, index=False)
    st.download_button("📥 ЗАВАНТАЖИТИ ПЛАН + КОЕФІЦІЄНТИ (EXCEL)", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d%m')}.xlsx", use_container_width=True)

    # ГРАФІК З КОЕФІЦІЄНТОМ
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Forecast_MW'], name="Теорія (Сайт)", line=dict(dash='dot', color='gray')))
    fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['AI_MW'], name="План AI", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    fig.add_trace(go.Scatter(x=df_f['Time'], y=df_f['AI_Ratio'], name="Коефіцієнт корекції (0-1)", yaxis="y2", line=dict(color='#ffeb3b', width=2)))
    
    fig.update_layout(
        template="plotly_dark", height=500, margin=dict(l=0,r=0,t=20,b=0),
        yaxis2=dict(title="Коефіцієнт", overlaying='y', side='right', range=[0, 1.2], showgrid=False),
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right")
    )
    st.plotly_chart(fig, use_container_width=True)

with t2:
    if day_forecast:
        st.subheader("Прогноз погоди Нікополь (10 днів)")
        def get_icon(name):
            icons = {"rain": "🌧️", "cloudy": "☁️", "partly-cloudy-day": "⛅", "clear-day": "☀️", "wind": "💨", "snow": "❄️"}
            return icons.get(name, "🌡️")
        cols = st.columns(len(day_forecast))
        for i, d in enumerate(day_forecast):
            with cols[i]:
                bg = "rgba(255, 75, 75, 0.15)" if d['Вітер'] > 12 else "rgba(255, 255, 255, 0.05)"
                st.markdown(f"""<div style='background:{bg}; padding:10px; border-radius:12px; text-align:center; border:1px solid rgba(255,255,255,0.1);'><p style='margin:0; font-size:12px; color:gray;'>{d['Дата']}</p><p style='margin:5px 0; font-size:25px;'>{get_icon(d['Icon'])}</p><p style='margin:0; font-weight:bold;'>{d['Макс']:.0f}°</p><p style='margin:0; font-size:11px; color:#00d4ff;'>{d['Вітер']:.0f} м/с</p></div>""", unsafe_allow_html=True)
        st.markdown("---")
        st.dataframe(pd.DataFrame(day_forecast)[['Дата', 'Умови', 'Мін', 'Макс', 'Опади', 'Вітер']], hide_index=True, use_container_width=True)

with t3:
    if 'df_h' in locals() and not df_h.empty:
        st.write("### Погодинна карта похибок ШІ")
        df_h['Ratio'] = (df_h['Fact_MW'] / df_h['Forecast_MW']).fillna(0).clip(0, 2)
        # Матриця середніх коефіцієнтів по годинах
        hourly_map = df_h[df_h['Hour'].between(7,19)].groupby('Hour')['Ratio'].mean().reset_index()
        fig_m = go.Figure(go.Bar(x=hourly_map['Hour'], y=hourly_map['Ratio'], marker_color='#ffeb3b'))
        fig_m.update_layout(template="plotly_dark", title="Середній реальний коефіцієнт виробітки по годинах (Факт/Теорія)", yaxis_title="Коефіцієнт")
        st.plotly_chart(fig_m, use_container_width=True)

with t4:
    if 'df_h' in locals(): st.dataframe(df_h.tail(20), use_container_width=True)

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.О. Колесник & SkyGrid AI</div>", unsafe_allow_html=True)
