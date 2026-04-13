import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

# Імпорт наших модулів
from weather_service import fetch_weather_data
from model_engine import train_and_get_insights
from ui_components import draw_main_chart, draw_metrics, draw_learning_insights

# 1. ОСНОВНІ НАЛАШТУВАННЯ
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 2. ОТРИМАННЯ ДАНИХ ПОГОДИ
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # 3. ЗАВАНТАЖЕННЯ БАЗИ ДАНИХ З GITHUB
        # Додаємо мітку часу v=..., щоб уникнути старого кешу GitHub
        url_base = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url_base)
        df_h['Time'] = pd.to_datetime(df_h['Time'])
        
        # 4. РОБОТА "МОЗКУ" (ШІ)
        # Отримуємо прогноз, точність, важливість факторів та історію помилок
        predictions, accuracy, importance, error_history = train_and_get_insights(df_h, df_f)
        df_f['AI_MW'] = predictions.astype(float)
        
        # Нічне обнулення (з 21:00 до 05:00)
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0

        # 5. ІНТЕРФЕЙС
        st.title("☀️ SkyGrid Solar AI")
        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

        with tabs[0]:
            # Верхні метрики на 3 дні
            draw_metrics(df_f, now_ua, timedelta)
            
            # Головний графік (Прогноз сайту vs ШІ)
            draw_main_chart(df_f)
            
            # Експорт у Excel
            output = io.BytesIO()
            excel_df = df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].copy()
            excel_df.columns = ['Час', 'Сайт (МВт)', 'ШІ (МВт)']
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                excel_df.to_excel(writer, index=False)
            st.download_button("📥 Завантажити План Excel", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx")

        with tabs[1]:
            # Візуалізація навчання моделі
            if importance is not None:
                draw_learning_insights(accuracy, importance, error_history)
            else:
                st.warning("Зачекайте... Потрібно більше даних у базі для аналізу роботи ШІ (мінімум 50 годин з Фактом).")
                st.info(f"Зараз у базі: {len(df_h[df_h['Fact_MW'].notna()])} годин з фактичними даними.")

        with tabs[2]:
            st.subheader("📑 Останні дані в системі")
            st.write("Ці дані використовуються для щогодинного перенавчання моделі.")
            st.dataframe(df_h.tail(24), use_container_width=True)

    except Exception as e:
        st.error(f"⚠️ Помилка логіки додатка: {e}")
        st.info("Перевірте структуру файлу solar_ai_base.csv на GitHub.")
else:
    st.error("❌ Не вдалося отримати прогноз погоди.")
    if st.button("🔄 Оновити дані"):
        st.cache_data.clear()
        st.rerun()
