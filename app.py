import streamlit as st
import pandas as pd
import time, io, pytz, json
import gspread
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials

from weather_service import fetch_weather_data, calc_forecast_mw
from dashboard_components import draw_main_chart, draw_metrics, draw_weather_strip
from ui_components import draw_training_tab, draw_base_tab, draw_meteo_tab, draw_plan_tab

# Налаштування сторiнки
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
PLAN_SHEET_ID = "1U8639UXFyZUNzMOg6BHcg_gDAX_JS9g7fpBkdXOpODw"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
LOGO_URL = "https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/logo.gif"
SETTINGS_SHEET_NAME = "Settings"
DEFAULT_CAPACITY_MW = 12.5

MONTHS_UK = {
    1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
    5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
    9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
}


def draw_app_header(logo_url):
    st.markdown(
        f"""
        <style>
        div[data-testid="stTabBar"] {{
            border-bottom: 1px solid rgba(255,255,255,0.06);
            gap: 8px;
        }}
        div[data-testid="stTabBar"] button {{
            color: #64748b !important;
            font-weight: 650 !important;
            font-size: 14px !important;
            border: none !important;
            padding: 10px 14px !important;
        }}
        div[data-testid="stTabBar"] button[aria-selected="true"] {{
            color: #ffb800 !important;
            background: rgba(255,184,0,0.06) !important;
            border-bottom: 2px solid #ffb800 !important;
        }}
        div[data-testid="stTabBarHighlight"] {{
            background-color: #ffb800 !important;
        }}
        .app-shell-header {{
            background: linear-gradient(135deg, rgba(17,22,34,0.98) 0%, rgba(11,17,26,0.98) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 18px 22px;
            margin: 10px 0 18px;
            box-shadow: 0 18px 36px rgba(0,0,0,0.28);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
        }}
        .app-brand {{
            display: flex;
            align-items: center;
            gap: 14px;
            min-width: 0;
        }}
        .app-brand__mark {{
            width: 42px;
            height: 42px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(255,184,0,0.14);
            color: #ffb800;
            box-shadow: 0 0 24px rgba(255,184,0,0.24);
            font-size: 22px;
            font-weight: 800;
        }}
        .app-brand__title {{
            font-size: 27px;
            line-height: 1.05;
            font-weight: 800;
            background: linear-gradient(90deg, #ffffff 0%, #ffb800 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            white-space: nowrap;
        }}
        .app-brand__subtitle {{
            color: rgba(255,255,255,0.44);
            font-size: 11px;
            margin-top: 5px;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }}
        .partner-card {{
            background: rgba(255,255,255,0.025);
            border: 1px solid rgba(255,255,255,0.07);
            border-radius: 8px;
            padding: 10px 14px;
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 260px;
            justify-content: flex-start;
        }}
        .partner-card img {{
            width: 38px;
            height: 38px;
            object-fit: contain;
        }}
        .partner-card__name {{
            color: rgba(255,255,255,0.86);
            font-size: 12px;
            line-height: 1.25;
            font-weight: 750;
        }}
        .partner-card__link {{
            color: rgba(255,255,255,0.42);
            font-size: 10px;
            text-decoration: none;
        }}
        @media (max-width: 900px) {{
            .app-shell-header {{
                align-items: flex-start;
                flex-direction: column;
            }}
            .app-brand__title {{
                font-size: 24px;
                white-space: normal;
            }}
            .partner-card {{
                width: 100%;
                min-width: 0;
            }}
        }}
        </style>
        <div class="app-shell-header">
            <div class="app-brand">
                <div class="app-brand__mark">☼</div>
                <div>
                    <div class="app-brand__title">SkyGrid Solar AI</div>
                    <div class="app-brand__subtitle">Система моніторингу та прогнозування сонячної генерації</div>
                </div>
            </div>
            <div class="partner-card">
                <img src="{logo_url}" alt="НЗФ logo">
                <div>
                    <div class="partner-card__name">Нікопольський завод феросплавів</div>
                    <a class="partner-card__link" href="https://www.nzf.com.ua" target="_blank">nzf.com.ua</a>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def open_main_spreadsheet():
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def get_or_create_settings_ws(sh):
    try:
        return sh.worksheet(SETTINGS_SHEET_NAME)
    except Exception:
        ws = sh.add_worksheet(title=SETTINGS_SHEET_NAME, rows=10, cols=2)
        ws.update("A1:B2", [["Key", "Value"], ["Capacity_MW", DEFAULT_CAPACITY_MW]])
        return ws


def save_setting_value(ws, key, value):
    rows = ws.get_all_records()

    for idx, row in enumerate(rows, start=2):
        if str(row.get("Key", "")).strip() == key:
            ws.update(values=[[key, value]], range_name=f"A{idx}:B{idx}")
            return

    next_row = len(rows) + 2
    if ws.row_count < next_row:
        ws.resize(rows=next_row + 5, cols=max(ws.col_count, 2))
    ws.update(values=[[key, value]], range_name=f"A{next_row}:B{next_row}")


@st.cache_data(ttl=300)
def load_capacity_from_sheets():
    try:
        sh = open_main_spreadsheet()
        ws = get_or_create_settings_ws(sh)
        rows = ws.get_all_records()
        for row in rows:
            if str(row.get("Key", "")).strip() == "Capacity_MW":
                value = str(row.get("Value", DEFAULT_CAPACITY_MW)).replace(",", ".").strip()
                capacity = float(value)
                if 1.0 <= capacity <= 100.0:
                    return capacity
        save_setting_value(ws, "Capacity_MW", DEFAULT_CAPACITY_MW)
    except Exception as e:
        st.warning(f"Не вдалося прочитати збережену потужність СЕС: {e}")
    return DEFAULT_CAPACITY_MW

def save_capacity_to_sheets(capacity_mw: float):
    sh = open_main_spreadsheet()
    ws = get_or_create_settings_ws(sh)
    save_setting_value(ws, "Capacity_MW", round(float(capacity_mw), 3))
    load_capacity_from_sheets.clear()

@st.cache_data(ttl=300)
def load_base_from_sheets():
    try:
        sh = open_main_spreadsheet()
        data = sh.sheet1.get_all_records()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df['Time'] = pd.to_datetime(df['Time'])
        num_cols = [
            'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb',
            'Fact_MW', 'Capacity_MW', 'AI_Forecast_MW',
            'Forecast_Error_MW', 'Forecast_Error_Pct',
            'AI_Error_MW', 'AI_Error_Pct'
        ]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(',', '.').str.strip(),
                    errors='coerce'
                ).fillna(0)
        return df
    except Exception as e:
        st.error(f"Помилка читання Google Sheet: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_plan_from_sheets(month: int, year: int, nominal_kw: float):
    sheet_name = f"{MONTHS_UK[month]} {str(year)[2:]}"
    try:
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        gc = gspread.authorize(creds)
        try:
            sh = gc.open_by_key(PLAN_SHEET_ID)
        except Exception as e:
            st.error(f"Немає доступу до таблиці плану: {type(e).__name__}: {e}")
            return pd.DataFrame()
        try:
            sheet_titles = [ws.title for ws in sh.worksheets()]
        except Exception as e:
            st.error(f"Не вдалось отримати список аркушів: {e}")
            return pd.DataFrame()
        if sheet_name not in sheet_titles:
            st.error(f"Аркуш '{sheet_name}' не знайдено. Доступні: {sheet_titles}")
            return pd.DataFrame()
        ws = sh.worksheet(sheet_name)
        raw = ws.get_all_values()
        df_raw = pd.DataFrame(raw)
        data = df_raw.iloc[4:, [1, 2] + list(range(3, 27))].copy()
        data.columns = ['Nominal', 'День'] + [f'П{i}' for i in range(1, 25)]
        for col in data.columns:
            data[col] = data[col].astype(str).str.replace(' ', '').str.replace(' ', '').str.replace(',', '.').str.strip()
            data[col] = pd.to_numeric(data[col], errors='coerce')
        nominals = data['Nominal'].dropna().unique()
        nominal_kw_val = nominal_kw * 1000
        closest = min(nominals, key=lambda x: abs(x - nominal_kw_val)) if len(nominals) > 0 else None
        if closest is None:
            st.error("Не знайдено номінал генерації в таблиці")
            return pd.DataFrame()
        plan = data[(data['Nominal'] == closest) & (data['День'] >= 1) & (data['День'] <= 31)].copy()
        plan = plan.drop_duplicates(subset=['День'])
        rows = []
        for _, row in plan.iterrows():
            day = int(row['День'])
            for h in range(1, 25):
                val = row.get(f'П{h}', 0)
                if pd.notna(val):
                    rows.append({'Time': datetime(year, month, day, h - 1, 0), 'Plan_MW': round(float(val) / 1000, 3)})
        if not rows:
            st.error("Дані плану порожні після парсингу")
            return pd.DataFrame()
        result = pd.DataFrame(rows)
        result['Time'] = pd.to_datetime(result['Time'])
        return result
    except Exception as e:
        st.error(f"Помилка завантаження плану: {type(e).__name__}: {e}")
        return pd.DataFrame()

# --- Заголовок ---
st.sidebar.markdown("🚀 **Status: SkyGrid_Active**")

draw_app_header(LOGO_URL)
col_title, col_spacer, col_logo = st.columns([5, 1, 2])
if False:
    st.markdown("# ☀️ SkyGrid Solar AI")
    st.markdown("<span style='color:gray; font-size:13px;'>Система моніторингу та прогнозування сонячної генерації</span>", unsafe_allow_html=True)
if False:
    st.markdown(f"""<div style='display:flex; align-items:center; justify-content:flex-end; gap:12px; padding-top:8px;'>
<img src='{LOGO_URL}' width='48' style='vertical-align:middle;'/>
<div style='text-align:left; line-height:1.3;'>
<div style='font-weight:600; font-size:14px;'>Нікопольський завод</div>
<div style='font-weight:600; font-size:14px;'>феросплавів</div>
<div style='font-size:11px; color:gray;'><a href='https://www.nzf.com.ua' target='_blank' style='color:gray; text-decoration:none;'>nzf.com.ua</a></div>
</div></div>""", unsafe_allow_html=True)

st.write("")

# 1. Завантаження погоди
df_f = fetch_weather_data()

if not df_f.empty:
    try:
        # 2. База історичних даних
        df_h = load_base_from_sheets()
        if df_h.empty:
            st.warning("База даних порожня або недоступна.")
            st.stop()

        # 3. Вкладки
        tabs = st.tabs(["Моніторинг", "Навчання", "База", "Метео", "План"])

        with tabs[0]:
            saved_capacity_mw = load_capacity_from_sheets()
            col_cap, col_info = st.columns([1, 3])
            with col_cap:
                capacity_mw = st.number_input(
                    "⚡ Потужність СЕС (МВт)",
                    min_value=1.0, max_value=100.0,
                    value=float(saved_capacity_mw), step=0.5,
                    key="capacity_mw",
                    help="Змінюй при введенні нових черг СЕС"
                )
                if abs(float(capacity_mw) - float(saved_capacity_mw)) > 0.001:
                    try:
                        save_capacity_to_sheets(capacity_mw)
                        st.success("Потужність СЕС збережено")
                    except Exception as e:
                        st.error(f"Не вдалося зберегти потужність СЕС: {e}")
            with col_info:
                st.markdown(f"<br>Прогноз розраховано для **{capacity_mw} МВт** · Нікополь", unsafe_allow_html=True)

            df_f['Capacity_MW'] = capacity_mw
            if 'Capacity_MW' not in df_h.columns:
                df_h['Capacity_MW'] = capacity_mw

            # Forecast_MW для графіка (прогноз сайту): Rad * 0.0114 * scale
            df_f = calc_forecast_mw(df_f, capacity_mw, kef=1.0)

            # ВАЖЛИВО:
            # Streamlit-додаток більше НЕ навчає модель при відкритті сторінки.
            # AI-прогноз бере тільки з Google Sheet, куди його записує collector.py.
            # Це прибирає конфлікт між двома різними моделями і робить прогноз чесним:
            # collector.py створив AI_Forecast_MW наперед → app.py тільки показав його.
            if 'AI_Forecast_MW' not in df_h.columns:
                df_h['AI_Forecast_MW'] = 0.0

            df_ai = df_h[['Time', 'AI_Forecast_MW']].copy()
            df_ai['Time'] = pd.to_datetime(df_ai['Time'])
            df_f['Time'] = pd.to_datetime(df_f['Time'])

            df_f = df_f.merge(df_ai, on='Time', how='left')
            ai_from_sheet = pd.to_numeric(df_f['AI_Forecast_MW'], errors='coerce').fillna(0)
            df_f['AI_MW'] = df_f['Forecast_MW']
            df_f.loc[ai_from_sheet > 0, 'AI_MW'] = ai_from_sheet[ai_from_sheet > 0]

            # Нічні години і незначна радіація → 0
            if 'Rad' in df_f.columns:
                df_f.loc[df_f['Rad'] < 5, 'AI_MW'] = 0.0
                df_f.loc[df_f['Rad'] < 5, 'Forecast_MW'] = 0.0

            # Дані для вкладки "Навчання" тепер формуються з уже збережених помилок,
            # а не через повторне навчання моделі в app.py.
            draw_metrics(df_f, df_h, now_ua, timedelta)
            st.write("")
            draw_weather_strip(df_f, now_ua, timedelta)

            st.write("")
            title_col, download_col = st.columns([3, 1])
            with title_col:
                st.markdown("##### Погодинний прогноз генерації на 3 дні")
            with download_col:
                output = io.BytesIO()
                export_from = pd.Timestamp(now_ua)
                export_to = export_from + pd.Timedelta(hours=72)
                df_export = df_f[(df_f['Time'] >= export_from) & (df_f['Time'] < export_to)].copy()
                export_cols = [
                    'Time', 'AI_MW', 'Forecast_MW',
                    'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'
                ]
                df_export = df_export[[col for col in export_cols if col in df_export.columns]]
                df_export = df_export.rename(columns={
                    'Time': 'Дата/Час',
                    'AI_MW': 'Прогнозована потужність ШІ, МВт',
                    'Forecast_MW': 'Базовий прогноз сайту, МВт',
                    'CloudCover': 'Очікувана хмарність, %',
                    'Temp': 'Температура, °C',
                    'WindSpeed': 'Швидкість вітру',
                    'PrecipProb': 'Ймовірність опадів, %',
                })
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False, sheet_name='Hourly_Forecast')
                st.download_button(
                    label="📥 Завантажити погодинний прогноз (.xlsx)",
                    data=output.getvalue(),
                    file_name=f"SkyGrid_Hourly_Forecast_{now_ua.strftime('%d_%m_%Y')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            draw_main_chart(df_f, now_ua)

        with tabs[1]:
            draw_training_tab(df_h)

        with tabs[2]:
            draw_base_tab(df_h)

        with tabs[3]:
            draw_meteo_tab(df_f)

        with tabs[4]:
            df_plan = load_plan_from_sheets(now_ua.month, now_ua.year, capacity_mw)
            draw_plan_tab(df_h, df_f, df_plan, now_ua)

    except Exception as e:
        st.error(f"Критична помилка додатка: {e}")
else:
    st.warning("Не вдалося отримати дані про погоду.")

# --- Підпис розробника ---
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:gray; font-size:12px;'>"
    "SkyGrid Solar AI v2.0 · Розробник: "
    "<a href='https://github.com/SergejKolesnik/Solar-Monitoring-System' target='_blank' style='color:gray;'>Sergej Kolesnik</a>"
    "</div>",
    unsafe_allow_html=True
        )
