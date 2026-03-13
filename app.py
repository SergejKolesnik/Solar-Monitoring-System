import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime
import time
import pytz
from io import BytesIO

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="Solar AI Nikopol v3.6.4", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# Стилізація CSS (адаптивна)
st.markdown("""
    <style>
    div[data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 700; }
    .stPlotlyChart { border-radius: 15px; border: 1px solid rgba(128,128,128,0.2); }
    .ai-card { background: rgba(0, 255, 127, 0.05); border: 1px solid #00ff7f; border-radius: 10px; padding: 15px; }
    .footer { position: fixed; bottom: 10px; right: 20px; color: gray; font-size: 11px; z-index: 1000; }
    .status-tag { background: rgba(128,128,128,0.1); padding: 5px 15px; border-radius: 20px; border: 1px solid rgba(128,128,128,0.2); font-size: 13px; }
    </style>
    """, unsafe_allow_html=True)

# 2. ФУНКЦІЇ ДАНИХ
@st.cache_data(ttl=600)
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation&timezone=auto&past_days=7&forecast_days=3"
    try:
        res = requests.get(url).json()
        h = res['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m'],
            'Rain': h['precipitation']
        })
        # Корекція часу (UTC -> Kyiv - 2h)
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None) - pd.Timedelta(hours=2)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00115 * (1 - df['Clouds']/100 * 0.2)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

# 3. ЛОГІКА ШІ ТА ФАКТУ
df_all = get_weather_data()
df_fact = None
ai_bias, last_update, days_learned = 1.0, "No data", 0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    last_date = df_fact['Time'].dt.date.max()
    last_update = last_date.strftime("%d.%m.%Y")
    days_learned = len(df_fact['Time'].dt.date.unique())
    f_day = df_fact[df_fact['Time'].dt.date == last_date]
    p_day = df_all[df_all['Time'].dt.date == last_date]
    if not f_day.empty and not p_day.empty:
        actual_sum = f_day['Fact_MW'].sum()
        base_pred = (p_day['Radiation'] * 11.4 * 0.00115 * (1 - p_day['Clouds']/100 * 0.2)).sum()
        if base_pred > 0: ai_bias = actual_sum / base_pred
except: pass

if df_all is not None:
    df_all['Power_MW'] = df_all['Power_MW'] * ai_bias

# 4. ШАПКА (HEADER)
col_l, col_r = st.columns([1, 4])
with col_l:
    st.image("https://www.nzf.com.ua/img/logo.gif", width=120)
with col_r:
    st.title("Solar AI Monitor: Nikopol v3.6.4")
    st.markdown(f"<div style='display:flex; gap:10px;'><span class='status-tag'>📅 Останні дані: <b>{last_update}</b></span><span class='status-tag'>🧠 Досвід ШІ: <b>{days_learned} днів</b></span></div>", unsafe_allow_html=True)

# 5. ОСНОВНИЙ КОНТЕНТ
if df_all is not None:
    now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
    df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
    st.markdown("---")
    m1, m2, m3 = st.columns(3)
    with m1: st.metric("План (Сьогодні) / Forecast", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:.2f}x bias")
    with m2: 
        cur_h = now_ua.hour
        t_row = df_today[df_today['Time'].dt.hour == cur_h]
        t_now = t_row['Temp'].values[0] if not t_row.empty else 0
        st.metric("Температура / Temp", f"{t_now}°C")
    with m3: st.metric("Потужність / Capacity", "11.4 MW Online")

    # ГРАФІК З АДАПТИВНОЮ ТЕМОЮ
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].copy()
    
    # Опади
    fig1.add_trace(go.Bar(x=df_f['Time'], y=df_f['Rain'], name="Опади / Rain (mm)", marker_color='rgba(0, 120, 255, 0.3)'))
    # Прогноз
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="ШІ План (MW)", fill='tozeroy', line=dict(color='#2ecc71', width=3), fillcolor='rgba(46, 204, 113, 0.2)'))
    # Температура
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Temp'], name="Темп (°C)", line=dict(color='#e74c3c', width=1.5, dash='dot')), secondary_y=True)

    # ВАЖЛИВО: Видаляємо жорстку прив'язку до dark mode для адаптивності
    fig1.update_layout(
        height=480,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", y=1.1, x=1, xanchor="right"),
        hovermode="x unified",
        paper_bgcolor='rgba(0,0,0,0)', # Прозорий фон
        plot_bgcolor='rgba(0,0,0,0)',
    )
    fig1.update_xaxes(showgrid=True, gridcolor='rgba(128,128,128,0.2)', tickformat="%H:%M\n%d.%m")
    fig1.update_yaxes(showgrid=True, gridcolor='rgba(128,128,128,0.2)', secondary_y=False)
    fig1.update_yaxes(showgrid=False, secondary_y=True)

    st.plotly_chart(fig1, use_container_width=True, theme="streamlit") # Використовуємо тему Streamlit

    # КНОПКА EXCEL
    df_ex = df_f[['Time', 'Power_MW', 'Temp', 'Rain', 'Clouds']].head(72).copy()
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
        df_ex.to_excel(wr, index=False, sheet_name='Forecast')
    st.download_button(label="📥 Завантажити План Excel / Download Excel Forecast", data=out.getvalue(), file_name=f"Solar_AI_Nikopol_Plan.xlsx")

st.markdown(f"<div class='footer'>Developed by Sergii Kolesnyk | Powered by Gemini AI v3.6.4</div>", unsafe_allow_html=True)

# АНАЛІТИКА
if df_fact is not None:
    with st.expander("📊 Аналіз точності ШІ / AI Accuracy Analysis"):
        df_p_c = df_all[df_all['Time'].dt.date == last_date]
        df_f_c = df_fact[df_fact['Time'].dt.date == last_date]
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df_p_c['Time'], y=df_p_c['Power_MW'], name="ШІ План", line=dict(color='#2ecc71', dash='dot')))
        fig2.add_trace(go.Scatter(x=df_f_c['Time'], y=df_f_c['Fact_MW'], name="Факт", line=dict(color='#e74c3c', width=3)))
        fig2.update_layout(height=300, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig2, use_container_width=True, theme="streamlit")
