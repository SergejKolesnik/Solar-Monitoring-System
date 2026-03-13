import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime
import time
import pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Solar AI Nikopol v3.7.4", layout="wide", initial_sidebar_state="collapsed")
UA_TZ = pytz.timezone('Europe/Kyiv')

# 2. СТИЛІЗАЦІЯ
st.markdown("""
    <style>
    .block-container { padding: 1rem 2rem; }
    .progress-bg { background: rgba(255,255,255,0.1); border-radius: 10px; height: 12px; width: 180px; display: inline-block; vertical-align: middle; overflow: hidden; margin-left: 10px; border: 1px solid rgba(0,255,127,0.3); }
    .progress-fill { background: linear-gradient(90deg, #00ff7f, #00d4ff); height: 100%; border-radius: 10px; }
    .weather-row { display: flex !important; flex-direction: row !important; justify-content: space-between !important; width: 100%; gap: 6px; margin: 15px 0; }
    .weather-card-industrial { flex: 1; background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(0, 212, 255, 0.3); border-radius: 12px; padding: 12px 5px; text-align: center; min-width: 0; }
    .day-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 10px; margin-top: 10px; }
    .day-card-industrial { background: rgba(255,255,255,0.05); border: 1px solid rgba(0, 212, 255, 0.4); border-radius: 15px; padding: 15px 10px; text-align: center; }
    .footer { position: fixed; bottom: 10px; right: 20px; color: gray; font-size: 12px; }
    </style>
    """, unsafe_allow_html=True)

# 3. ФУНКЦІЇ ДАНИХ
@st.cache_data(ttl=300)
def get_weather_data():
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m,precipitation&timezone=auto&forecast_days=10"
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
        # Корекція часу: Open-Meteo дає в UTC
        df['Time'] = df['Time'].dt.tz_localize('UTC').dt.tz_convert(UA_TZ).dt.tz_localize(None)
        return df
    except: return None

# 4. ЛОГІКА ШІ
df_all = get_weather_data()
df_fact = None
ai_bias, last_update, days_learned = 1.0, "Очікування", 0

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time']).dt.floor('H')
    
    # Визначаємо актуальний Bias
    last_date = df_fact['Time'].dt.date.max()
    last_update = last_date.strftime("%d.%m.%Y")
    days_learned = len(df_fact['Time'].dt.date.unique())
    
    f_day = df_fact[df_fact['Time'].dt.date == last_date]
    p_day = df_all[df_all['Time'].dt.date == last_date] if df_all is not None else pd.DataFrame()
    
    if not f_day.empty and not p_day.empty:
        actual_sum = f_day['Fact_MW'].sum()
        base_pred = (p_day['Radiation'] * 11.4 * 0.00115 * (1 - p_day['Clouds']/100 * 0.2)).sum()
        if base_pred > 0: ai_bias = actual_sum / base_pred
except: pass

if df_all is not None:
    df_all['Power_MW'] = df_all['Radiation'] * 11.4 * 0.00115 * (1 - df_all['Clouds']/100 * 0.2) * ai_bias
    df_all.loc[df_all['Power_MW'] < 0, 'Power_MW'] = 0

# 5. ШАПКА
col_logo, col_title = st.columns([0.6, 5])
with col_logo: st.image("https://www.nzf.com.ua/img/logo.gif", width=100)
with col_title:
    prog_val = min(days_learned / 365 * 100, 100)
    st.markdown(f"<div style='display:flex; justify-content:space-between; align-items:center; padding-top:10px;'><h1 style='margin:0; font-size:32px;'>SkyGrid: Solar AI Nikopol</h1><div style='display:flex; gap:15px; align-items:center;'><span style='font-size:16px;'>📅 АСКОЕ: <b>{last_update}</b></span><span style='font-size:16px;'>🧠 ШІ: <b>{days_learned} дн.</b> <div class='progress-bg'><div class='progress-fill' style='width:{prog_val}%;'></div></div></span></div></div>", unsafe_allow_html=True)

# 6. ВКЛАДКИ
tab_main, tab_weather = st.tabs(["🚀 МОНІТОРИНГ ТА НАВЧАННЯ", "🌦 ПРОГНОЗ ПОГОДИ"])

with tab_main:
    if df_all is not None:
        now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
        df_today = df_all[df_all['Time'].dt.date == now_ua.date()]
        
        m1, m2, m3 = st.columns(3)
        with m1: st.metric("ШІ ПЛАН (СЬОГОДНІ)", f"{df_today['Power_MW'].sum():.1f} MWh", f"Bias: {ai_bias:.2f}x")
        with m2: 
            cur_h = now_ua.hour
            t_row = df_today[df_today['Time'].dt.hour == cur_h]
            t_now = t_row['Temp'].values[0] if not t_row.empty else 0
            st.metric("ТЕМПЕРАТУРА", f"{t_now}°C")
        with m3: st.metric("СТАТУС СЕС", "11.4 MW Online")

        # Верхній графік (План)
        st.subheader("📈 Оперативний план генерації (72 години)")
        fig1 = make_subplots(specs=[[{"secondary_y": True}]])
        df_f = df_all[df_all['Time'] >= pd.Timestamp(now_ua.date())].head(72).copy()
        fig1.add_trace(go.Bar(x=df_f['Time'], y=df_f['Rain'], name="Опади", marker_color='rgba(0, 150, 255, 0.3)'))
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Power_MW'], name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f', width=4)))
        fig1.add_trace(go.Scatter(x=df_f['Time'], y=df_f['Temp'], name="Темп", line=dict(color='#ff4b4b', width=2, dash='dot')), secondary_y=True)
        fig1.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
        st.plotly_chart(fig1, use_container_width=True)

        # Нижній графік (Навчання)
        st.markdown("---")
        st.subheader("📊 Аналіз точності ШІ та дані АСКОЕ (Навчання)")
        
        if df_fact is not None:
            # Жорстка синхронізація часу для графіку
            df_hist_fact = df_fact.tail(72).copy()
            df_hist_pred = df_all[df_all['Time'].isin(df_hist_fact['Time'])].copy()
            
            fig_learn = go.Figure()
            # План (завжди малюємо першим для фону)
            if not df_hist_pred.empty:
                fig_learn.add_trace(go.Scatter(x=df_hist_pred['Time'], y=df_hist_pred['Power_MW'], name="План ШІ", line=dict(color='#00d4ff', width=2, dash='dash')))
            
            # Факт АСКОЕ (основна лінія)
            fig_learn.add_trace(go.Scatter(x=df_hist_fact['Time'], y=df_hist_fact['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#00ff7f', width=4)))
            
            # Область дельти (якщо є обидва набори)
            if not df_hist_pred.empty:
                merged = pd.merge(df_hist_fact, df_hist_pred, on='Time')
                fig_learn.add_trace(go.Scatter(x=merged['Time'], y=merged['Power_MW'], fill='tonexty', mode='none', fillcolor='rgba(255, 255, 255, 0.05)', name="Дельта корекції", showlegend=False))

            fig_learn.update_layout(height=380, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
            st.plotly_chart(fig_learn, use_container_width=True)
        else:
            st.info("Завантажте файл solar_ai_base.csv в репозиторій для відображення аналітики.")

with tab_weather:
    st.markdown("### 🕒 ПОГОДИННИЙ ПРОГНОЗ (24 ГОДИНИ)")
    cards_html = '<div class="weather-row">'
    for _, row in df_today.iterrows():
        cards_html += f'<div class="weather-card-industrial"><div style="color:#00d4ff;font-weight:bold;">{row["Time"].strftime("%H:%M")}</div><div style="font-size:22px;font-weight:900;">{row["Temp"]:.1f}°</div><div style="font-size:12px;color:#bbb;">☁️{row["Clouds"]}% | 💧{row["Rain"]:.1f}</div></div>'
    cards_html += '</div>'
    st.markdown(cards_html, unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 📅 МЕТЕОПРОГНОЗ НА 10 ДНІВ")
    df_10d = df_all.groupby(df_all['Time'].dt.date).agg({'Temp':['min','max'], 'Rain':'sum', 'Clouds':'mean'})
    day_html = '<div class="day-grid">'
    for date, row in df_10d.iterrows():
        day_html += f'<div class="day-card-industrial"><div style="color:#00d4ff;font-weight:bold;">{date.strftime("%d.%m")}</div><div style="font-size:26px;font-weight:800;">{row[("Temp","max")]:.0f}°</div><div style="color:#aaa;">/{row[("Temp","min")]:.0f}°</div><div style="font-size:13px;margin-top:5px;">☁️{row[("Clouds","mean")]:.0f}% <span style="color:#00d4ff;">💧{row[("Rain","sum")]:.1f}</span></div></div>'
    day_html += '</div>'
    st.markdown(day_html, unsafe_allow_html=True)

st.markdown(f"<div class='footer'>Developed by Sergii Kolesnyk | АТ 'НЗФ' © 2026</div>", unsafe_allow_html=True)
