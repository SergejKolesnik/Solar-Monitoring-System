import streamlit as st
import pandas as pd
import time, io, pytz
from datetime import datetime, timedelta

from weather_service import fetch_weather_data
from model_engine import train_and_get_insights
from ui_components import draw_main_chart, draw_metrics, draw_training_tab

# Налаштування сторінки
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

st.sidebar.markdown("🚀 **Status: SkyGrid_Active**")
st.title("☀️ SkyGrid Solar AI")

# 1. Завантаження погоди
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # 2. Завантаження бази з GitHub
        url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url)
        df_h['Time'] = pd.to_datetime(df_h['Time'])

        # 3. Виклик моделі
        try:
            results = train_and_get_insights(df_h, df_f)

            if isinstance(results, tuple) and len(results) == 6:
                predictions, accuracy, importance, scatter_data, pivot_error, comparison_df = results
            elif isinstance(results, tuple) and len(results) == 4:
                predictions, accuracy, importance, scatter_data = results
                pivot_error, comparison_df = 0.0, None
            else:
                predictions = results[0] if isinstance(results, tuple) else results
                accuracy, importance, scatter_data, pivot_error, comparison_df = 0.0, None, None, 0.0, None

            df_f['AI_MW'] = predictions

        except Exception as model_err:
            st.error(f"⚠️ Помилка логіки моделі: {model_err}")
            st.stop()

        # 4. Корекція нічного часу
        df_f.loc[df_f['Rad'] < 5, ['AI_MW', 'Forecast_MW']] = 0.0

        # 5. Вкладки
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

            st.download_button(
                label="📥 Завантажити План в Excel",
                data=output.getvalue(),
                file_name=f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with tabs[1]:
            draw_training_tab(df_h, accuracy, importance, scatter_data, pivot_error, comparison_df)

        with tabs[2]:
            st.subheader("📑 Останні записи в базі даних")
            st.dataframe(df_h.tail(48).sort_values('Time', ascending=False), use_container_width=True)

    except Exception as e:
        st.error(f"❌ Критична помилка додатка: {e}")
else:
    st.warning("Не вдалося отримати дані про погоду.")
