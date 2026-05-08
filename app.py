import streamlit as st
import pandas as pd
import time, io, pytz, json
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

from weather_service import fetch_weather_data
from model_engine import train_and_get_insights
from ui_components import draw_main_chart, draw_metrics, draw_training_tab, draw_base_tab, draw_meteo_tab

# Налаштування сторінки
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

@st.cache_data(ttl=300)
def load_base_from_sheets():
    try:
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        data = sh.sheet1.get_all_records()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df['Time'] = pd.to_datetime(df['Time'])
        return df
    except Exception as e:
        st.error(f"❌ Помилка читання Google Sheet: {e}")
        return pd.DataFrame()

st.sidebar.markdown("🚀 **Status: SkyGrid_Active**")
st.title("☀️ SkyGrid Solar AI")

# 1. Завантаження погоди
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # 2. Завантаження бази з Google Sheets
        df_h = load_base_from_sheets()

        if df_h.empty:
            st.warning("⚠️ База даних порожня або недоступна.")
            st.stop()

        # 3. Вкладки
        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📅 БАЗА", "🌤 МЕТЕО"])

        with tabs[0]:
            # --- Перемикач потужності ---
            col_cap, col_info = st.columns([1, 3])
            with col_cap:
                capacity_mw = st.number_input(
                    "⚡ Потужність СЕС (МВт)",
                    min_value=1.0,
                    max_value=100.0,
                    value=12.5,
                    step=0.5,
                    help="Змінюй при введенні нових черг СЕС"
                )
            with col_info:
                st.markdown(f"<br>Прогноз розраховано для **{capacity_mw} МВт** · Нікополь", unsafe_allow_html=True)

            # 4. Додаємо Capacity_MW
            df_f['Capacity_MW'] = capacity_mw
            if 'Capacity_MW' not in df_h.columns:
                df_h['Capacity_MW'] = capacity_mw

            # 5. Виклик моделі
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

            # 6. Корекція нічного часу
            df_f.loc[df_f['Rad'] < 5, ['AI_MW', 'Forecast_MW']] = 0.0

            # 7. Метрики та графік
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
            draw_base_tab(df_h)

        with tabs[3]:
            draw_meteo_tab(df_f)

    except Exception as e:
        st.error(f"❌ Критична помилка додатка: {e}")
else:
    st.warning("Не вдалося отримати дані про погоду.")
