import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

# Імпорт модулів
from weather_service import fetch_weather_data
from model_engine import train_and_get_insights
from ui_components import draw_main_chart, draw_metrics, draw_learning_insights

# --- МОНІТОРИНГ АКТИВНОСТІ ---
def ping_monitor():
    """Записує активність у логи для перевірки роботи UptimeRobot"""
    now = datetime.now(pytz.timezone('Europe/Kyiv'))
    # Ви побачите це в Manage App -> Logs
    print(f"📡 [UPTIME CHECK] Система активна: {now.strftime('%d.%m %H:%M:%S')}")

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
ping_monitor()

UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# КРИТИЧНО: Слово для UptimeRobot (якщо використовуєте Keyword монітор)
st.sidebar.markdown("🚀 **Status: SkyGrid_Active**") 

st.title("☀️ SkyGrid Solar AI")

# --- ГОЛОВНА ЛОГІКА ---
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # Завантаження бази
        url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url)
        df_h['Time'] = pd.to_datetime(df_h['Time'])
        
        # Робота моделі
        predictions, accuracy, importance, error_history, pivot_error = train_and_get_insights(df_h, df_f)
        df_f['AI_MW'] = predictions
        
        # Нічне обнулення
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0

        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])
        
        with tabs[0]:
            draw_metrics(df_f, now_ua, timedelta)
            draw_main_chart(df_f)
            
            st.write("---")
            # Кнопка Excel
            output = io.BytesIO()
            df_export = df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].copy()
            df_export.columns = ['Час', 'Прогноз сайту (МВт)', 'План ШІ (МВт)']
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_export.to_excel(writer, index=False, sheet_name='Solar_Plan')
            st.download_button(
                label="📥 Завантажити План в Excel",
                data=output.getvalue(),
                file_name=f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with tabs[1]:
            if importance is not None:
                draw_learning_insights(accuracy, importance, error_history, pivot_error)
        
        with tabs[2]:
            st.subheader("📑 Поточний стан бази")
            st.dataframe(df_h.tail(48), use_container_width=True)
            
    except Exception as e:
        st.error(f"⚠️ Помилка завантаження бази: {e}")
else:
    st.error("❌ Метеосервіс не відповідає.")
