import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

from weather_service import fetch_weather_data
from model_engine import train_and_get_insights
from ui_components import draw_main_chart, draw_metrics, draw_learning_insights

# Налаштування сторінки
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

st.title("☀️ SkyGrid Solar AI")

# 1. ОТРИМАННЯ ПОГОДИ
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # 2. ЗАВАНТАЖЕННЯ БАЗИ (з обходом кешу GitHub)
        url_base = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url_base)
        df_h['Time'] = pd.to_datetime(df_h['Time'])
        
        # 3. РОБОТА ШІ (Захищений блок)
        try:
            predictions, accuracy, importance, error_history = train_and_get_insights(df_h, df_f)
            df_f['AI_MW'] = predictions
        except Exception as e:
            st.error(f"⚠️ Тимчасова помилка розрахунків ШІ: {e}")
            df_f['AI_MW'] = df_f['Forecast_MW'] # Використовуємо сайт як страховку
            accuracy, importance, error_history = 0.0, None, None

        # Нічне обнулення
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0

        # 4. ІНТЕРФЕЙС
        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

        with tabs[0]:
            draw_metrics(df_f, now_ua, timedelta)
            draw_main_chart(df_f)
            
            # Кнопка Excel
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].to_excel(writer, index=False)
            st.download_button("📥 Завантажити План", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx")

        with tabs[1]:
            if importance is not None and not importance.empty:
                draw_learning_insights(accuracy, importance, error_history)
            else:
                st.warning("📊 ШІ ще не бачить достатньо спільних факторів у базі та прогноз погоди для побудови графіків.")

        with tabs[2]:
            st.subheader("📑 Останні дані в системі")
            st.dataframe(df_h.tail(24), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Помилка завантаження файлів системи: {e}")
else:
    st.error("❌ Не вдалося отримати прогноз погоди.")
