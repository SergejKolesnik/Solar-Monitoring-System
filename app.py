import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime
import time
import pytz
import io

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI v15.3", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

if 'weather_cache' not in st.session_state: st.session_state.weather_cache = None

@st.cache_data(ttl=3600)
def fetch_weather():
    api_key = st.secrets["WEATHER_API_KEY"]
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,tempmax,tempmin,cloudcover,solarradiation,windspeed,winddir,precipprob,conditions,icon&key={api_key}&contentType=json"
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list, d_list = [], []
            for d in data['days']:
                d_list.append({
                    'Дата': pd.to_datetime(d['datetime']).strftime('%d.%m'),
                    'Макс': d.get('tempmax'),
                    'Мін': d.get('tempmin'),
                    'Опади': d.get('precipprob'),
                    'Вітер': d.get('windspeed'),
                    'Напрямок': d.get('winddir'),
                    'Умови': d.get('conditions'),
                    'Icon': d.get('icon', 'clear-day')
                })
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': hr.get('solarradiation', 0),
                        'Clouds': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0),
                        'WindSpd': hr.get('windspeed', 0)
                    })
            df = pd.DataFrame(h_list)
            return df, d_list, "OK"
        return None, None, f"API Error {res.status_code}"
    except Exception as e: return None, None, str(e)

# 2. ДАНІ ТА ОБРОБКА БАЗИ
df_raw, day_forecast, status = fetch_weather()
if df_raw is None and st.session_state.weather_cache:
    df_f, day_forecast = st.session_state.weather_cache
else:
    df_f = df_raw
    st.session_state.weather_cache = (df_raw, day_forecast)

if df_f is None: st.error("🔌 Пробудження системи..."); st.stop()

now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias, exp_hours = 1.0, 0
daily_stats = pd.DataFrame()

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    df_h['Time'] = pd.to_datetime(df_h['Time'])
    
    # Синхронізація колонок
    if 'CloudCover' in df_h.columns: df_h = df_h.rename(columns={'CloudCover': 'Clouds'})
    
    # Розрахунок коефіцієнта та годин
    df_h_mar = df_h[(df_h['Time'].dt.year == 2026) & (df_h['Time'].dt.month == 3)].copy()
    exp_hours = len(df_h_mar.dropna(subset=['Fact_MW']))
    
    df_v = df_h_mar.dropna(subset=['Fact_MW', 'Forecast_MW']).tail(72)
    if not df_v.empty: 
        ai_bias = df_v['Fact_MW'].sum() / df_v['Forecast_MW'].sum()
    
    # Підготовка даних для ГРАФІКА
    df_h_mar['Date'] = df_h_mar['Time'].dt.date
    daily_stats = df_h_mar.groupby('Date').agg({'Fact_MW':'sum','Forecast_MW':'sum'}).reset_index()
    daily_stats = daily_stats.dropna(subset=['Fact_MW', 'Forecast_MW'], how='all')
except Exception as e:
    st.warning(f"Помилка бази даних: {e}")

# 3. РОЗРАХУНОК AI ПРОГНОЗУ
df_f['AI_MW'] = df_f['Rad'] * 11.4 * 0.001 * ai_bias
df_f['Raw_MW'] = df_f['Rad'] * 11.4 * 0.001
s_ai_sum = df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum()
s_raw_sum = df_f[df_f['Time'].dt.date == now_ua.date()]['Raw_MW'].sum()

# 4. ШАПКА
col_title, col_logo = st.columns([4, 1])
with col_title:
    st.title("☀️ SkyGrid Solar AI")
    st.caption(f"Прогноз на {now_ua.strftime('%d.%m.%Y')} • Нікополь • NZF")
with col_logo:
    st.markdown(f'<a href="https://www.nzf.com.ua/main.aspx" target="_blank"><img src="https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/nzf_logo.png" style="width:100px; border-radius:10px; float:right;"></a>', unsafe_allow_html=True)

t1, t2 = st.tabs(["📊 АНАЛІТИКА ТА ПРОГНОЗ", "🌦 МЕТЕОЦЕНТР НІКОПОЛЬ"])

with t1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("ПРОГНОЗ AI", f"{s_ai_sum:.1f} MWh", delta=f"{ai_bias:.2f}x")
    c2.metric("ПРОГНОЗ САЙТУ", f"{s_raw_sum:.1f} MWh")
    c3.metric("БАЗА ДОСВІДУ", f"{exp_hours} год")
    c4.metric("КОЕФІЦІЄНТ AI", f"{ai_bias:.2f}x")

    # КНОПКА EXCEL
    st.markdown("<br>", unsafe_allow_html=True)
    df_p = df_f[df_f['Time'] >= pd.Timestamp(now_ua.date())].head(72).copy()
    excel_io = io.BytesIO()
    with pd.ExcelWriter(excel_io, engine='xlsxwriter') as writer:
        df_p[['Time', 'AI_MW', 'Raw_MW']].rename(columns={'AI_MW': 'План AI (MWh)', 'Raw_MW': 'Сайт (MWh)'}).to_excel(writer, index=False)
    st.download_button(label="📥 ЗАВАНТАЖИТИ ПЛАН В EXCEL", data=excel_io.getvalue(), file_name=f"Solar_NZF_{now_ua.strftime('%d%m')}.xlsx", use_container_width=True)

    # ОСНОВНИЙ ГРАФІК
    if not daily_stats.empty:
        fig_d = go.Figure()
        # 1. Сайт
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW'], name="Сайт", marker_color='gray', opacity=0.4))
        # 2. AI
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Forecast_MW']*ai_bias, name="План AI", marker_color='#1f77b4'))
        # 3. Факт
        fig_d.add_trace(go.Bar(x=daily_stats['Date'], y=daily_stats['Fact_MW'], name="Факт АСКОЕ", marker_color='#00ff7f', text=daily_stats['Fact_MW'].round(1), textposition='outside'))
        
        fig_d.update_layout(barmode='group', height=400, template="plotly_dark", margin=dict(l=0,r=0,t=30,b=0), legend=dict(orientation="h", y=1.1, x=1, xanchor="right"))
        st.plotly_chart(fig_d, use_container_width=True)
    else:
        st.info("Дані для графіка завантажуються...")

    with st.expander("🧠 AI Training Center (Heatmap)"):
        if 'df_h_mar' in locals() and not df_h_mar.empty:
            df_heat = df_h_mar.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
            if not df_heat.empty:
                df_heat['Година'] = df_heat['Time'].dt.hour
                df_heat['Дата'] = df_heat['Time'].dt.strftime('%d.%m')
                df_heat['Похибка_МВт'] = df_heat['Fact_MW'] - (df_heat['Forecast_MW'] * ai_bias)
                pivot = df_heat[(df_heat['Година']>=6) & (df_heat['Година']<=19)].pivot(index='Дата', columns='Година', values='Похибка_МВт')
                fig_hm = px.imshow(pivot, labels=dict(x="Година", y="Дата", color="Δ МВт"), color_continuous_scale="RdBu_r", aspect="auto")
                fig_hm.update_layout(height=350, template="plotly_dark")
                st.plotly_chart(fig_hm, use_container_width=True)

with t2:
    st.subheader("🌦 Прогноз погоди: Нікополь (10 днів)")
    if day_forecast:
        def get_icon(name):
            icons = {"rain": "🌧️", "cloudy": "☁️", "partly-cloudy-day": "⛅", "clear-day": "☀️", "wind": "💨", "snow": "❄️"}
            return icons.get(name, "🌡️")

        st.markdown("<br>", unsafe_allow_html=True)
        cols = st.columns(len(day_forecast))
        for i, d in enumerate(day_forecast):
            with cols[i]:
                # Кольорова підсвітка
                bg = "rgba(255, 75, 75, 0.2)" if float(d['Вітер']) > 12 else "rgba(255, 255, 255, 0.05)"
                border = "rgba(255, 75, 75, 0.5)" if float(d['Вітер'] or 0) > 12 else "rgba(255, 255, 255, 0.1)"
                st.markdown(f"""
                <div style='background:{bg}; padding:10px; border-radius:12px; text-align:center; border:1px solid {border}; height: 140px;'>
                    <p style='margin:0; font-size:12px; color:gray;'>{d['Дата']}</p>
                    <p style='margin:5px 0; font-size:25px;'>{get_icon(d['Icon'])}</p>
                    <p style='margin:0; font-weight:bold; font-size:16px;'>{d['Макс']:.0f}°</p>
                    <p style='margin:0; font-size:11px; color:#00d4ff;'>{d['Вітер']:.0f} м/с</p>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")
        df_10 = pd.DataFrame(day_forecast)
        st.dataframe(df_10[['Дата', 'Умови', 'Мін', 'Макс', 'Опади', 'Вітер']], hide_index=True, use_container_width=True)

st.markdown("---")
st.markdown("<div style='text-align:center; color:gray; font-size:12px;'><b>Розробка:</b> С.О. Колесник & SkyGrid AI • 2026</div>", unsafe_allow_html=True)
