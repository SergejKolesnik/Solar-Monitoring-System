import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time

# ТЕСТОВА ЛАБОРАТОРІЯ - НЕ ВПЛИВАЄ НА ОСНОВНУ БАЗУ
st.set_page_config(page_title="SkyGrid TEST LAB", layout="wide")

st.title("🧪 Полігон: Тестування графіку та Excel")
st.info("Ця версія працює в ізольованому режимі і тільки читає дані.")

# 1. ТЕСТОВИЙ ЗБІР МЕТЕО (без запису в базу)
def fetch_test_weather():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,solarradiation&key={api_key}&contentType=json"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': float(hr.get('solarradiation', 0))
                    })
            df = pd.DataFrame(h_list)
            # Розрахунок прогнозу сайту
            df['Прогноз сайту (МВт)'] = (df['Rad'] * 11.4 * 0.001).astype(float)
            return df
    except: pass
    return pd.DataFrame()

df_test = fetch_test_weather()

# 2. ВІЗУАЛІЗАЦІЯ (Шукаємо, куди зникає лінія)
if not df_test.empty:
    st.write("### Перевірка наявності даних:")
    st.write(df_test.head(5)) # Покаже нам, чи є цифри в колонці

    fig = go.Figure()
    
    # Малюємо сірий пунктир
    fig.add_trace(go.Scatter(
        x=df_test['Time'].head(72), 
        y=df_test['Прогноз сайту (МВт)'].head(72), 
        name="ТЕСТ: Прогноз сайту", 
        line=dict(dash='dot', color='orange', width=3) # Помаранчевий, щоб відрізнити
    ))
    
    fig.update_layout(title="Тестовий графік (має бути помаранчева пунктирна лінія)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Метеодані не завантажились!")
