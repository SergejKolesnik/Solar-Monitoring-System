import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time, io, pytz
from datetime import datetime, timedelta

# 1. НАЛАШТУВАННЯ (Як на Полігоні)
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

def get_data():
    try:
        if "WEATHER_API_KEY" not in st.secrets:
            st.error("Ключ WEATHER_API_KEY не знайдено в Secrets!")
            return pd.DataFrame()
            
        api_key = st.secrets["WEATHER_API_KEY"]
        # Використовуємо перевірене посилання з Полігону
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next2days?unitGroup=metric&key={api_key}&contentType=json"
        res = requests.get(url, timeout=10)
        data = res.json()
        h_list = []
        for d in data['days']:
            for hr in d['hours']:
                h_list.append({
                    'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                    'Rad': float(hr.get('solarradiation', 0))
                })
        df = pd.DataFrame(h_list)
        # Назви колонок для стабільності
        df['Прогноз сайту (МВт)'] = df['Rad'] * 11.4 * 0.001
        # Тимчасова імітація ШІ (поки не підключимо модель назад)
        df['Прогноз ШІ (МВт)'] = df['Прогноз сайту (МВт)'] * 1.02
        return df
    except Exception as e:
        st.error(f"Помилка завантаження: {e}")
        return pd.DataFrame()

# --- ЗАПУСК ---
st.title("☀️ SkyGrid Solar AI (Stable)")

df = get_data()

if not df.empty:
    # Обнуляємо ніч (21:00 - 05:00)
    night = (df['Time'].dt.hour < 5) | (df['Time'].dt.hour > 20)
    df.loc[night, ['Прогноз ШІ (МВт)', 'Прогноз сайту (МВт)']] = 0.0

    # Метрики
    c1, c2 = st.columns(2)
    t_today = now_ua.date()
    d_today = df[df['Time'].dt.date == t_today]
    if not d_today.empty:
        c1.metric("Сьогодні (ШІ)", f"{d_today['Прогноз ШІ (МВт)'].sum():.2f} МВт·год")
        c2.metric("Сьогодні (Сайт)", f"{d_today['Прогноз сайту (МВт)'].sum():.2f} МВт·год")

    # ГРАФІК (Точна копія працюючого Полігону)
    fig = go.Figure()
    
    # 1. Сірий пунктир (Сайт)
    fig.add_trace(go.Scatter(
        x=df['Time'], y=df['Прогноз сайту (МВт)'],
        name="Прогноз сайту",
        line=dict(dash='dot', color='gray', width=2)
    ))

    # 2. Зелена область (ШІ)
    fig.add_trace(go.Scatter(
        x=df['Time'], y=df['Прогноз ШІ (МВт)'],
        name="План ШІ",
        fill='tozeroy',
        line=dict(color='#00ff7f', width=3)
    ))

    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=10, r=10, t=10, b=10)
    )

    st.plotly_chart(fig, use_container_width=True)
    
    # Кнопка Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df[['Time', 'Прогноз сайту (МВт)', 'Прогноз ШІ (МВт)']].to_excel(writer, index=False)
    st.download_button("📥 Завантажити План", output.getvalue(), "Solar_Plan.xlsx")
