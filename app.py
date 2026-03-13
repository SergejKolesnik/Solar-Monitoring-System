import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import time
import pytz
from io import BytesIO

st.set_page_config(page_title="Solar AI Nikopol v3.4.1", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 1. СТИЛІЗАЦІЯ
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
    .ai-card { background: rgba(0, 255, 127, 0.05); border: 1px solid #00ff7f; border-radius: 10px; padding: 20px; }
    .stDownloadButton button { width: 100%; background-color: #00ff7f !important; color: black !important; font-weight: bold !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. ОТРИМАННЯ МЕТЕОДАНИХ
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
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None)
        return df
    except: return None

# --- ЗАВАНТАЖЕННЯ ТА АДАПТАЦІЯ ШІ ---
df_all = get_weather_data()
df_fact = None
ai_bias = 1.0 

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    
    last_date = df_fact['Time'].dt.date.max()
    f_day = df_fact[df_fact['Time'].dt.date == last_date]
    p_day = df_all[df_all['Time'].dt.date == last_date]
    
    if not f_day.empty and not p_day.empty:
        actual_sum = f_day['Fact_MW'].sum()
        base_pred = (p_day['Radiation'] * 11.4 * 0.00115 * (1 - p_day['Clouds']/100 * 0.2)).sum()
        if base_pred > 0: ai_bias = actual_sum / base_pred
except: pass

if df_all is not None:
    df_all['Power_MW'] = (df_all['Radiation'] * 11.4 * 0.00115 * (1 - df_all['Clouds']/100 * 0.2)) * ai_bias
    df_all.loc[df_all['Power_MW'] < 0, 'Power_MW'] = 0

# --- ГРАФІК ---
st.title("☀️ Solar AI Monitor: Nikopol v3.4.1")

if df_all is not None:
    now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
    df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
    
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("Адаптований прогноз", f"{df_today['Power_MW'].sum():.1f} MWh", f"{ai_bias:.2f}x")
    with c2: st.metric("Температура", f"{df_today.iloc[now_ua.hour]['Temp']}°C")
    with c3: st.metric("Самонавчання", "Активне")

    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].copy()

    fig1.add_trace(go.Bar(x=df_f['Time'], y=df_f['Rain'], name="Опади (мм)", marker_color='rgba(0, 150, 255, 0.5)'))
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="Прогноз (MW)", fill='tozeroy', line=dict(color='#00ff7f', width=3), fillcolor='rgba(0, 255, 127, 0.2)'))
    fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Temp'], name="Темп (°C)", line=dict(color='#ff4b4b', width=1, dash='dot')), secondary_y=True)

    fig1.update_layout(template="plotly_dark", height=450, legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig1, use_container_width=True)

    # --- ЕКСПОРТ В EXCEL ---
    st.subheader("📦 Експорт плану на 3 дні")
    
    df_excel = df_f[['Time', 'Power_MW', 'Temp', 'Rain', 'Clouds']].copy()
    df_excel['Date'] = df_excel['Time'].dt.date
    df_excel.columns = ['Дата_Час', 'Прогноз_МВт', 'Темп_C', 'Опади_мм', 'Хмарність_%', 'Дата']
    
    output = BytesIO()
    # Створюємо файл Excel
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_excel.to_excel(writer, index=False, sheet_name='Hourly_Plan')
        
        # Додаємо лист із підсумками по днях
        summary = df_excel.groupby('Дата')['Прогноз_МВт'].sum().reset_index()
        summary.columns = ['Дата', 'Загальна_генерація_МВт_год']
        summary.to_excel(writer, index=False, sheet_name='Daily_Summary')

    excel_data = output.getvalue()

    st.download_button(
        label="📥 Завантажити графік прогнозу в Excel (.xlsx)",
        data=excel_data,
        file_name=f"Solar_AI_Plan_{now_ua.strftime('%d_%m')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# --- БЛОК АНАЛІТИКИ ---
if df_fact is not None:
    st.markdown("---")
    st.header("🤖 Аналітика ШІ")
    last_date = df_fact['Time'].dt.date.max()
    df_p_comp = df_all[df_all['Time'].dt.date == last_date]
    df_f_comp = df_fact[df_fact['Time'].dt.date == last_date]
    
    col_a, col_b = st.columns([2, 1])
    with col_a:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df_p_comp['Time'], y=df_p_comp['Power_MW'], name="ШІ (Навчений)", line=dict(color='#00ff7f', width=2, dash='dot')))
        fig2.add_trace(go.Scatter(x=df_f_comp['Time'], y=df_f_comp['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#e74c3c', width=3)))
        fig2.update_layout(template="plotly_dark", title=f"Порівняння за {last_date}", height=350)
        st.plotly_chart(fig2, use_container_width=True)
    with col_b:
        st.markdown(f"<div class='ai-card'><b>💡 Корекція:</b> {ai_bias:.3f}x<br>Модель автоматично підлаштована під вчорашній виробіток.</div>", unsafe_allow_html=True)
