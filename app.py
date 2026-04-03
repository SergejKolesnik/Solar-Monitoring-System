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

# 1. КОНФІГУРАЦІЯ ТА СТИЛІЗАЦІЯ (DARK MODE FORCE)
st.set_page_config(page_title="SkyGrid Solar AI v18.9", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

st.markdown("""
    <style>
    .stApp { background-color: #0E1117; color: #FFFFFF; }
    div[data-testid="stMetricValue"] { color: #00ff7f !important; }
    .stAlert { border-radius: 10px; border: 1px solid #ff4b4b; }
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
                    'Макс': d.get('tempmax'), 'Мін': d.get('tempmin'),
                    'Опади': d.get('precipprob'), 'Вітер': d.get('windspeed'),
                    'Умови': d.get('conditions'), 'Icon': d.get('icon', 'clear-day')
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
    # Вчимося тільки на тих рядках, де є і прогноз, і факт
    df_train = df_base.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
    df_train = df_train[df_train['Fact_MW'] > 0] # Тільки коли станція працювала
    
    if len(df_train) < 24: return None, None, len(df_train), 0
    
    features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    X = df_train[features].fillna(0)
    y = df_train['Fact_MW']
    
    model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
    model.fit(X, y)
    accuracy = r2_score(y, model.predict(X)) * 100
    return model, df_train, len(df_train), accuracy

# --- ПІДГОТОВКА ДАНИХ ---
df_f, day_forecast, weather_status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    # Універсальне чищення дати від DST для Streamlit
    df_h['Time'] = df_h['Time'].astype(str).str.replace('DST', '').str.strip()
    df_h['Time'] = pd.to_datetime(df_h['Time'])
    
    model, df_trained_data, data_count, model_acc = train_solar_engine(df_h)
    
    if df_f is not None:
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        if model:
            features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            df_f['AI_MW'] = model.predict(df_f[features].fillna(0))
            df_f.loc[(df_f['Hour'] < 5) | (df_f['Hour'] > 20), 'AI_MW'] = 0
            df_f['AI_MW'] = df_f['AI_MW'].clip(lower=0)
            model_status = f"✅ ШІ в строю ({data_count} год)"
        else:
            df_f['AI_MW'] = df_f['Forecast_MW']
            model_status = f"⏳ Навчання... ({data_count}/24)"
except:
    model_status = "⚠️ Помилка бази"
    data_count, model_acc = 0, 0

# --- ІНТЕРФЕЙС ---
st.title("☀️ SkyGrid Solar AI v18.9")
st.caption(f"АТ «НЗФ» • Головний енергетик Колесник С.І. • {now_ua.strftime('%d.%m.%Y %H:%M')}")

t1, t2, t3, t4 = st.tabs(["📊 МОНІТОРИНГ", "🌦 МЕТЕОЦЕНТР", "🧠 МОДЕЛЬ ШІ", "📑 ДІАГНОСТИКА БАЗИ"])

with t1:
    # --- БЛОК САМОПЕРЕВІРКИ АКТУАЛЬНОСТІ ---
    if 'df_h' in locals() and not df_h.empty:
        last_ts = df_h['Time'].max()
        diff = now_ua - last_ts
        if diff.total_seconds() > 10800: # 3 години
            st.error(f"🚨 ДАНІ НЕ ОНОВЛЮЮТЬСЯ ВЖЕ {int(diff.total_seconds()//3600)} ГОД!")
            st.warning(f"Остання позначка в системі: {last_ts.strftime('%d.%m %H:%M')}. Перевірте GitHub Actions та АСКОЕ.")
        else:
            st.success(f"✅ Система синхронізована. Останні дані: {last_ts.strftime('%H:%M')}")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.2])
    days_list = [now_ua.date(), (now_ua + timedelta(days=1)).date(), (now_ua + timedelta(days=2)).date()]
    labels = ["СЬОГОДНІ", "ЗАВТРА", "ПІСЛЯЗАВТРА"]

    for i, col in enumerate([c1, c2, c3]):
        d_data = df_f[df_f['Time'].dt.date == days_list[i]]
        with col:
            st.metric(labels[i], f"{d_data['AI_MW'].sum():.1f} MWh", delta=f"Сайт: {d_data['Forecast_MW'].sum():.1f}")
            if st.button(f"👁️ Години", key=f"b_{i}"):
                st.table(d_data[['Time', 'AI_MW']].tail(12))

    with c4:
        st.write("**Статус:**", model_status)
        st.write(f"**Точність:** {model_acc:.1f}%")

    fig_main = go.Figure()
    fig_main.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), name="Сайт", line=dict(dash='dot', color='gray')))
    fig_main.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['AI_MW'].head(72), name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    fig_main.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig_main, use_container_width=True)

with t2:
    if day_forecast:
        f_cols = st.columns(len(day_forecast))
        for i, d in enumerate(day_forecast):
            with f_cols[i]:
                st.markdown(f"<div style='text-align:center; background:#1E2127; padding:10px; border-radius:10px;'><b>{d['Дата']}</b><br>🌡️ {d['Макс']}°<br>💨 {d['Вітер']}м/с</div>", unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(day_forecast), hide_index=True, use_container_width=True)

with t3:
    st.subheader("Прогрес навчання моделі")
    prog = min(data_count / 1000, 1.0)
    st.markdown(f"""<div style="width: 100%; background:#333; height:25px; border-radius:10px;"><div style="width:{prog*100}%; background:#00ff7f; height:100%; border-radius:10px;"></div></div>""", unsafe_allow_html=True)
    
    if 'df_h' in locals() and not df_h.empty:
        st.write("### Битва прогнозів (Останні 7 днів)")
        hist_data = df_h.copy()
        if model:
            feats = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
            hist_data['AI_MW'] = model.predict(hist_data[feats].fillna(0))
        
        perf = hist_data.groupby(hist_data['Time'].dt.date).agg({'Forecast_MW':'sum', 'AI_MW':'sum', 'Fact_MW':'sum'}).tail(7).reset_index()
        fig_b = go.Figure()
        fig_b.add_trace(go.Bar(x=perf['Time'], y=perf['Forecast_MW'], name="Сайт", marker_color='orange'))
        fig_b.add_trace(go.Bar(x=perf['Time'], y=perf['AI_MW'], name="План ШІ", marker_color='#1f77b4'))
        fig_b.add_trace(go.Bar(x=perf['Time'], y=perf['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f'))
        st.plotly_chart(fig_b, use_container_width=True)

with t4:
    st.subheader("🛠️ Технічний аудит бази даних")
    if 'df_h' in locals():
        col_a, col_b = st.columns(2)
        with col_a:
            st.write("**Останні записи:**")
            st.dataframe(df_h.tail(10))
        with col_b:
            # Перевірка на "дірки" у факті АСКОЕ
            missing = df_h[(df_h['Fact_MW'].isna()) | (df_h['Fact_MW'] == 0)].tail(20)
            if not missing.empty:
                st.error("⚠️ Виявлено пропуски Факту АСКОЕ!")
                st.write("ШІ не може вчитися на цих годинах:")
                st.dataframe(missing[['Time', 'Forecast_MW']])
            else:
                st.success("✅ Всі дані Факту завантажені коректно.")
        
        # Аналіз DST помилок
        st.info("💡 Підказка: Якщо дата містить 'DST', скрипт автоматично очищує її для коректного навчання.")

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'>SkyGrid Solar Intelligence System v18.9 • Powered by Sergej Kolesnik</div>", unsafe_allow_html=True)
