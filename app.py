import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

from weather_service import fetch_weather_data
from model_engine import train_and_predict
from ui_components import draw_main_chart, draw_metrics

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

df_f = fetch_weather_data()

if not df_f.empty:
    try:
        url_base = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url_base)
        
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds.astype(float)
        
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0

        st.title("☀️ SkyGrid Solar AI")
        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

        with tabs[0]:
            draw_metrics(df_f, now_ua, timedelta)
            draw_main_chart(df_f)
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].to_excel(writer, index=False)
            st.download_button("📥 Завантажити План", output.getvalue(), "Solar_Plan.xlsx")

        with tabs[1]:
            st.subheader(f"🧠 Точність: {accuracy:.1f}%")
            st.info(f"База містить {len(df_h)} годин спостережень.")

        with tabs[2]:
            st.dataframe(df_h.tail(20), use_container_width=True)

    except Exception as e:
        st.error(f"Помилка обробки: {e}")
else:
    st.error("Дані погоди недоступні. Перевірте Secrets.")
