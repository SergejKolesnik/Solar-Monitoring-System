import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

from weather_service import fetch_weather_data
from model_engine import train_and_get_insights
from ui_components import draw_main_chart, draw_metrics, draw_learning_insights

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

st.sidebar.markdown("🚀 **Status: SkyGrid_Active**")
st.title("☀️ SkyGrid Solar AI")

df_f = fetch_weather_data()

if not df_f.empty:
    try:
        url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url)
        df_h['Time'] = pd.to_datetime(df_h['Time'])
        
        # ВИПРАВЛЕНО: Тепер приймаємо 6 параметрів
        predictions, accuracy, importance, error_history, pivot_error, comparison_df = train_and_get_insights(df_h, df_f)
        df_f['AI_MW'] = predictions
        
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0

        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])
        
        with tabs[0]:
            draw_metrics(df_f, now_ua, timedelta)
            draw_main_chart(df_f)
            st.write("---")
            output = io.BytesIO()
            df_export = df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].copy()
            df_export.columns = ['Час', 'Прогноз сайту (МВт)', 'План ШІ (МВт)']
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Solar_Plan')
            st.download_button(label="📥 Завантажити План в Excel", data=output.getvalue(), file_name=f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx")
        
        with tabs[1]:
            if importance is not None:
                draw_learning_insights(accuracy, importance, error_history, pivot_error, comparison_df)
        
        with tabs[2]:
            st.dataframe(df_h.tail(48), use_container_width=True)
            
    except Exception as e:
        st.error(f"⚠️ Помилка завантаження бази: {e}")
else:
    st.error("❌ Метеосервіс не відповідає.")
