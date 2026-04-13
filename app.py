import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

# Імпорт модулів (переконайтеся, що назви файлів збігаються)
try:
    from weather_service import fetch_weather_data
    from model_engine import train_and_get_insights
    from ui_components import draw_main_chart, draw_metrics, draw_learning_insights
except ImportError as e:
    st.error(f"Помилка імпорту модулів: {e}")

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 2. ПОЧАТОК ВІДОБРАЖЕННЯ
st.title("☀️ SkyGrid Solar AI")

# Завантаження погоди
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # Завантаження бази з GitHub (v=time для обходу кешу)
        url_base = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url_base)
        df_h['Time'] = pd.to_datetime(df_h['Time'])
        
        # --- БЕЗПЕЧНИЙ ВИКЛИК ШІ ---
        try:
            predictions, accuracy, importance, error_history = train_and_get_insights(df_h, df_f)
            df_f['AI_MW'] = predictions
        except Exception as ai_err:
            # Якщо мозок не спрацював - використовуємо прогноз сайту
            df_f['AI_MW'] = df_f['Forecast_MW']
            accuracy, importance, error_history = 0.0, None, None
            st.warning("⚠️ ШІ тимчасово використовує базовий прогноз через оновлення бази.")

        # Нічне обнулення (з 21:00 до 05:00)
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0

        # 3. ВКЛАДКИ ІНТЕРФЕЙСУ
        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

        with tabs[0]:
            # Верхні показники
            draw_metrics(df_f, now_ua, timedelta)
            # Головний графік
            draw_main_chart(df_f)
            
            # Кнопка Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].to_excel(writer, index=False)
            st.download_button("📥 Завантажити План", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx")

        with tabs[1]:
            # Аналітика навчання
            if importance is not None:
                draw_learning_insights(accuracy, importance, error_history)
            else:
                st.info("📊 Аналітика оновиться, коли база на GitHub отримає свіжі дані.")

        with tabs[2]:
            st.subheader("📑 Стан бази даних (Останні 24 години)")
            st.dataframe(df_h.tail(24), use_container_width=True)

    except Exception as e:
        st.error(f"Помилка завантаження бази: {e}")
else:
    st.error("❌ Не вдалося отримати дані погоди.")
