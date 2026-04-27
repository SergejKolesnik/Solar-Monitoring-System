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

st.sidebar.markdown("🚀 **Status: SkyGrid_Active**")
st.title("☀️ SkyGrid Solar AI")

# 1. Завантаження свіжої погоди
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # 2. Завантаження історичної бази з GitHub
        url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url)
        df_h['Time'] = pd.to_datetime(df_h['Time'])
        
        # 3. Навчання та отримання розширеної аналітики
        # Отримуємо: прогнози, точність R2, важливість факторів, дані для точок, помилку MSE та порівняння за 5 днів
        predictions, accuracy, importance, scatter_data, pivot_error, comparison_df = train_and_get_insights(df_h, df_f)
        
        df_f['AI_MW'] = predictions
        
        # Корекція нічного часу (обнулення генерації)
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0

        # Створення вкладок
        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])
        
        with tabs[0]:
            # Головна сторінка з метриками та графіком
            draw_metrics(df_f, now_ua, timedelta)
            draw_main_chart(df_f)
            
            st.write("---")
            # Експорт плану в Excel
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
            # Сторінка навчання (Аналітика "мізків" ШІ)
            st.subheader("🧠 Аналітика навчання нейронної моделі")
            
            # Рядок з ключовими метриками якості
            m1, m2, m3 = st.columns(3)
            m1.metric("Якість моделі (R²)", f"{accuracy:.1f}%", help="На скільки % ШІ зрозумів закономірності. Ідеал - 100%")
            m2.metric("Похибка (MSE)", f"{pivot_error:.4f}", help="Середня квадратна помилка. Чим менше число, тим краще")
            m3.metric("Активних факторів", len(importance) if importance is not None else 0)

            st.write("---")
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.write("📊 **Вплив факторів (Feature Importance)**")
                if importance is not None:
                    st.bar_chart(importance.set_index('Фактор'))
                    st.caption("Графік показує, які метеодані найбільше впливають на результат ШІ.")
                else:
                    st.info("Недостатньо даних для аналізу факторів")

            with col_right:
                st.write("🎯 **Діаграма точності (Факт vs План)**")
                if scatter_data is not None:
                    # Візуалізація того, як "Факт" збігається з "Планом ШІ"
                    st.scatter_chart(scatter_data, x='Факт', y='План_ШІ')
                    st.caption("Кожна точка — година. Якщо точки йдуть по діагоналі — ШІ працює ідеально.")
                else:
                    st.info("Чекаємо на накопичення даних для точкового аналізу")

            st.write("---")
            st.write("📅 **Ефективність за останні 5 днів (Добова сума, МВт)**")
            if comparison_df is not None:
                # Таблиця порівняння трьох джерел
                st.dataframe(comparison_df.style.highlight_max(axis=0, color='#1b5e20'), use_container_width=True)
                # Графік порівняння точності прогнозів за добу
                st.line_chart(comparison_df.set_index('Дата'))
            else:
                st.warning("Дані за останні 5 днів відсутні або некоректні")

        with tabs[2]:
            # Перегляд сирих даних бази
            st.subheader("📑 Останні записи в базі даних")
            st.dataframe(df_h.tail(48).sort_values('Time', ascending=False), use_container_width=True)
            st.info(f"Загальна кількість записів у навчальній базі: {len(df_h)}")

    except Exception as e:
        st.error(f"Помилка завантаження бази: {e}")
        st.info("Перевірте наявність файлу solar_ai_base.csv у вашому репозиторії GitHub.")

else:
    st.warning("Не вдалося отримати дані про погоду. Перевірте WEATHER_API_KEY.")
