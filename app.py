import streamlit as st
import pandas as pd
import time, io, pytz, json
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

from weather_service import fetch_weather_data
from model_engine import train_and_get_insights
from ui_components import draw_main_chart, draw_metrics, draw_training_tab, draw_base_tab, draw_meteo_tab, draw_plan_tab

# Налаштування сторінки
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
PLAN_SHEET_ID = "1U8639UXFyZUNzMOg6BHcg_gDAX_JS9g7fpBkdXOpODw"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
LOGO_URL = "https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/logo.gif"

MONTHS_UK = {
    1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
    5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
    9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
}


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


@st.cache_data(ttl=3600)
def load_plan_from_sheets(month: int, year: int, nominal_kw: float):
    """Читає план генерації з Google Sheet за поточний місяць через сервісний акаунт."""
    sheet_name = f"{MONTHS_UK[month]} {str(year)[2:]}"
    try:
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        gc = gspread.authorize(creds)

        # Спочатку перевіримо чи є доступ до таблиці
        try:
            sh = gc.open_by_key(PLAN_SHEET_ID)
        except Exception as e:
            st.error(f"❌ Немає доступу до таблиці плану: {type(e).__name__}: {e}")
            return pd.DataFrame()

        # Перевіримо список аркушів
        try:
            sheet_titles = [ws.title for ws in sh.worksheets()]
        except Exception as e:
            st.error(f"❌ Не вдалось отримати список аркушів: {e}")
            return pd.DataFrame()

        # Знаходимо потрібний аркуш
        if sheet_name not in sheet_titles:
            st.error(f"❌ Аркуш '{sheet_name}' не знайдено. Доступні: {sheet_titles}")
            return pd.DataFrame()

        ws = sh.worksheet(sheet_name)
        raw = ws.get_all_values()
        df_raw = pd.DataFrame(raw)

        # Колонка 1 = Номінал, колонка 2 = День, колонки 3-26 = П1-П24
        data = df_raw.iloc[4:, [1, 2] + list(range(3, 27))].copy()
        data.columns = ['Nominal', 'День'] + [f'П{i}' for i in range(1, 25)]

        for col in data.columns:
            data[col] = data[col].astype(str).str.replace(' ', '').str.replace('\xa0', '').str.replace(',', '.').str.strip()
            data[col] = pd.to_numeric(data[col], errors='coerce')

        nominals = data['Nominal'].dropna().unique()
        nominal_kw_val = nominal_kw * 1000
        closest = min(nominals, key=lambda x: abs(x - nominal_kw_val)) if len(nominals) > 0 else None

        if closest is None:
            st.error("❌ Не знайдено номінал генерації в таблиці")
            return pd.DataFrame()

        plan = data[(data['Nominal'] == closest) & (data['День'] >= 1) & (data['День'] <= 31)].copy()
        plan = plan.drop_duplicates(subset=['День'])

        rows = []
        for _, row in plan.iterrows():
            day = int(row['День'])
            for h in range(1, 25):
                val = row.get(f'П{h}', 0)
                if pd.notna(val):
                    rows.append({
                        'Time': datetime(year, month, day, h - 1, 0),
                        'Plan_MW': round(float(val) / 1000, 3)
                    })

        if not rows:
            st.error("❌ Дані плану порожні після парсингу")
            return pd.DataFrame()

        result = pd.DataFrame(rows)
        result['Time'] = pd.to_datetime(result['Time'])
        return result

    except Exception as e:
        st.error(f"❌ Помилка завантаження плану: {type(e).__name__}: {e}")
        return pd.DataFrame()


# --- Заголовок ---
st.sidebar.markdown("🚀 **Status: SkyGrid_Active**")

col_title, col_spacer, col_logo = st.columns([5, 1, 2])
with col_title:
    st.markdown("# ☀️ SkyGrid Solar AI")
    st.markdown("<span style='color:gray; font-size:13px;'>Система моніторингу та прогнозування сонячної генерації</span>", unsafe_allow_html=True)
with col_logo:
    st.markdown(
        f"""
        <div style='display:flex; align-items:center; justify-content:flex-end; gap:12px; padding-top:8px;'>
            <img src='{LOGO_URL}' width='48' style='vertical-align:middle;'/>
            <div style='text-align:left; line-height:1.3;'>
                <div style='font-weight:600; font-size:14px;'>Нікопольський завод</div>
                <div style='font-weight:600; font-size:14px;'>феросплавів</div>
                <div style='font-size:11px; color:gray;'><a href='https://www.nzf.com.ua' target='_blank' style='color:gray; text-decoration:none;'>nzf.com.ua</a></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("---")

# 1. Завантаження погоди
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # 2. Завантаження бази
        df_h = load_base_from_sheets()

        if df_h.empty:
            st.warning("⚠️ База даних порожня або недоступна.")
            st.stop()

        # 3. Вкладки
        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📅 БАЗА", "🌤 МЕТЕО", "📋 ПЛАН"])

        with tabs[0]:
            col_cap, col_info = st.columns([1, 3])
            with col_cap:
                capacity_mw = st.number_input(
                    "⚡ Потужність СЕС (МВт)",
                    min_value=1.0, max_value=100.0,
                    value=12.5, step=0.5,
                    help="Змінюй при введенні нових черг СЕС"
                )
            with col_info:
                st.markdown(f"<br>Прогноз розраховано для **{capacity_mw} МВт** · Нікополь", unsafe_allow_html=True)

            df_f['Capacity_MW'] = capacity_mw
            if 'Capacity_MW' not in df_h.columns:
                df_h['Capacity_MW'] = capacity_mw

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

            df_f.loc[df_f['Rad'] < 5, ['AI_MW', 'Forecast_MW']] = 0.0

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

        with tabs[4]:
            df_plan = load_plan_from_sheets(now_ua.month, now_ua.year, capacity_mw)
            draw_plan_tab(df_h, df_f, df_plan, now_ua)

    except Exception as e:
        st.error(f"❌ Критична помилка додатка: {e}")
else:
    st.warning("Не вдалося отримати дані про погоду.")

# --- Підпис розробника ---
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:gray; font-size:12px;'>"
    "SkyGrid Solar AI v1.0 · Розробник: "
    "<a href='https://github.com/SergejKolesnik/Solar-Monitoring-System' target='_blank' style='color:gray;'>Sergej Kolesnik</a>"
    "</div>",
    unsafe_allow_html=True
)
