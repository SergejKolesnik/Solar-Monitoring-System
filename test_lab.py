import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests

st.set_page_config(page_title="SkyGrid: ТЕСТ ГРАФІКИ", layout="wide")
st.title("🧪 Полігон: Перевірка двох ліній")

def get_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
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
        # Назви колонок точно як ми хочемо в фіналі
        df['Прогноз сайту (МВт)'] = df['Rad'] * 11.4 * 0.001
        # Імітуємо ШІ (просто трохи коригуємо дані для тесту)
        df['Прогноз ШІ (МВт)'] = df['Прогноз сайту (МВт)'] * 1.1 
        return df
    except Exception as e:
        st.error(f"Помилка: {e}")
        return pd.DataFrame()

df = get_data()

if not df.empty:
    fig = go.Figure()
    
    # 1. СІРИЙ ПУНКТИР (Сайт)
    fig.add_trace(go.Scatter(
        x=df['Time'], y=df['Прогноз сайту (МВт)'],
        name="Прогноз сайту",
        line=dict(dash='dot', color='gray', width=2)
    ))

    # 2. ЗЕЛЕНА ОБЛАСТЬ (ШІ)
    fig.add_trace(go.Scatter(
        x=df['Time'], y=df['Прогноз ШІ (МВт)'],
        name="Прогноз ШІ (тест)",
        fill='tozeroy',
        line=dict(color='#00ff7f', width=3)
    ))

    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=10, r=10, t=10, b=10)
    )

    st.plotly_chart(fig, use_container_width=True)
    st.success("Якщо ви бачите сірий пунктир ПІД зеленою зоною — графік повністю справний!")
