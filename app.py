import streamlit as st
import pandas as pd
import time, pytz
from datetime import datetime, timedelta

# Імпортуємо наші модулі
from model_engine import train_and_predict
from ui_components import draw_main_chart, draw_training_stats

st.set_page_config(page_title="SkyGrid Solar AI v21.0", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# ... (код fetch_weather залишаємо без змін) ...

df_f, day_forecast = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time']).dt.floor('h')
    
    if df_f is not None:
        # Розрахунок прогнозу сайту
        df_f['Forecast_MW'] = df_f['Rad'] * 11.4 * 0.001
        # Виклик ШІ
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds
        df_f.loc[(df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20), 'AI_MW'] = 0
except:
    df_h, accuracy = pd.DataFrame(), 0

st.title(f"☀️ SkyGrid Solar AI")
tabs = st.tabs(["📊 МОНІТОРИНГ", "🌦 МЕТЕОЦЕНТР", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with tabs[0]:
    # Відображення метрик
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d_date = (now_ua + timedelta(days=i)).date()
        d_data = df_f[df_f['Time'].dt.date == d_date]
        if not d_data.empty:
            col.metric(f"{d_date.strftime('%d.%m')}", f"{d_data['AI_MW'].sum():.1f} MWh")
    
    # Виклик графіку з ui_components
    draw_main_chart(df_f)

with tabs[2]:
    # Виклик статистики з ui_components
    draw_training_stats(df_h, accuracy)

with tabs[3]:
    st.dataframe(df_h.tail(50), use_container_width=True)
      
