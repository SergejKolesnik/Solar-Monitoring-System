import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta
from weather_service import fetch_weather_data
from model_engine import train_and_predict
from ui_components import draw_main_chart, draw_training_stats

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

df_f = fetch_weather_data()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

try:
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
    df_h = pd.read_csv(url)
    if not df_f.empty:
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds
        # Обнулення ночі
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0
except:
    df_h, accuracy = pd.DataFrame(), 0

# МЕТРИКИ, ГРАФІК ТА КНОПКА EXCEL
st.title("☀️ SkyGrid Solar AI")
tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

with tabs[0]:
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d_date = (now_ua + timedelta(days=i)).date()
        d_data = df_f[df_f['Time'].dt.date == d_date]
        if not d_data.empty:
            ai_s, si_s = d_data['AI_MW'].sum(), d_data['Forecast_MW'].sum()
            col.metric(f"{d_date.strftime('%d.%m')}", f"{ai_s:.2f} MWh", f"{ai_s-si_s:+.2f}")
    
    draw_main_chart(df_f)
    
    # Кнопка Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_f.head(72).to_excel(writer, index=False)
    st.download_button("📥 Скачати Excel", output.getvalue(), "Solar_Plan.xlsx")

with tabs[1]:
    draw_training_stats(df_h, accuracy)
