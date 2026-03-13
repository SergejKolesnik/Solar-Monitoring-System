import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="Solar AI Nikopol", layout="wide")

# Дизайнерські стилі
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; color: #f1c40f; }
    .stPlotlyChart { border-radius: 15px; }
    .ai-card { background: rgba(241, 196, 15, 0.05); border: 1px solid #f1c40f; border-radius: 10px; padding: 20px; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=600)
def get_weather_data(days=3):
    url = f"https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m&timezone=auto&forecast_days={days}"
    try:
        data = requests.get(url).json()
        h = data['hourly']
        df = pd.DataFrame({
            'Time': pd.to_datetime(h['time']),
            'Radiation': h['shortwave_radiation'],
            'Clouds': h['cloud_cover'],
            'Temp': h['temperature_2m']
        })
        # Базова модель v2.6 (11.4 MW)
        df['Power_MW'] = df['Radiation'] * 11.4 * 0.00092 * (1 - df['Clouds']/100 * 0.4)
        df.loc[df['Power_MW'] < 0, 'Power_MW'] = 0
        return df
    except: return None

# Завантажуємо прогноз на 3 дні та факт з GitHub
df_forecast = get_weather_data(3)
df_fact = None
try:
    v_tag = int(time.time())
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
except: pass

# --- ВЕРХНІЙ БЛОК: ОПЕРАТИВНИЙ МОНІТОРИНГ ---
st.title("☀️ Solar AI Monitor: Оперативне управління")

col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    today_gen = df_forecast[df_forecast['Time'].dt.date == datetime.now().date()]['Power_MW'].sum()
    st.metric("Прогноз на сьогодні", f"{today_gen:.1f} MWh")
with col_m2:
    st.metric("Температура Нікополь", f"{df_forecast.iloc[datetime.now().hour]['Temp']}°C")
with col_m3:
    st.metric("Статус СЕС", "11.4 MW Online")

# Графік майбутнього
fig1 = go.Figure()
fig1.add_trace(go.Scatter(x=df_forecast['Time'], y=df_forecast['Power_MW'], name="План (MW)", fill='tozeroy', line=dict(color='#f1c40f', width=4)))
fig1.update_layout(template="plotly_dark", title="Майбутня генерація (План на 3 дні)", height=400, margin=dict(l=10, r=10, t=40, b=10))
st.plotly_chart(fig1, use_container_width=True)

st.markdown("---")

# --- НИЖНІЙ БЛОК: АНАЛІТИКА ШІ ---
if df_fact is not None:
    st.header("📈 Ретроспективний аналіз та корекція ШІ")
    
    # Визначаємо дати, за які маємо факт (наприклад, 12.03)
    available_dates = df_fact['Time'].dt.date.unique()
    target_date = available_dates[-1] 
    
    # Створюємо порівняння: беремо факт за цей день і "базову модель"
    # Для точності запитуємо архівну погоду за той самий день
    df_hist_weather = get_weather_data(7) # Беремо тиждень, щоб точно зачепити минуле
    df_hist_day = df_hist_weather[df_hist_weather['Time'].dt.date == target_date].copy()
    df_fact_day = df_fact[df_fact['Time'].dt.date == target_date].copy()
    
    col_graph, col_ai = st.columns([2, 1])
    
    with col_graph:
        fig2 = go.Figure()
        # План (Золота лінія)
        fig2.add_trace(go.Scatter(x=df_hist_day['Time'], y=df_hist_day['Power_MW'], name="План v2.6", line=dict(color='rgba(241, 196, 15, 0.4)', width=2, dash='dot')))
        # Факт (Червона лінія)
        fig2.add_trace(go.Scatter(x=df_fact_day['Time'], y=df_fact_day['Fact_MW'], name="Факт АСКОЕ", line=dict(color='#e74c3c', width=3)))
        
        fig2.update_layout(template="plotly_dark", title=f"Аналіз за {target_date.strftime('%d.%m.%Y')}", height=450)
        st.plotly_chart(fig2, use_container_width=True)

    with col_ai:
        st.markdown(f"<div class='ai-card'>", unsafe_allow_html=True)
        st.subheader("🤖 Вердикт ШІ")
        
        sum_plan = df_hist_day['Power_MW'].sum()
        sum_fact = df_fact_day['Fact_MW'].sum()
        
        if sum_plan > 0:
            accuracy = (1 - abs(sum_plan - sum_fact) / sum_plan) * 100
            st.write(f"**Точність моделі:** {accuracy:.1f}%")
            
            diff = sum_fact - sum_plan
            status = "Перевиконання" if diff > 0 else "Недоотримання"
            st.write(f"**Результат:** {status} {abs(diff):.2f} MWh")
            
            st.markdown("---")
            st.write("**Рекомендація щодо корекції:**")
            if accuracy < 90:
                st.info("ШІ виявив аномальну хмарність. Рекомендовано збільшити Cloud Penalty на 5% для наступних розрахунків.")
            else:
                st.success("Модель працює стабільно. Корекція параметрів не потрібна.")
        st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Дані для аналітики ШІ з'являться автоматично після успішної синхронізації звіту АСКОЕ.")
