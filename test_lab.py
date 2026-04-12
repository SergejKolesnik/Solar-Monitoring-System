import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests

st.set_page_config(page_title="SkyGrid: ТЕСТ", layout="wide")

st.title("🧪 Тестовий стенд")

# 1. Спрощене отримання даних
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
        df['Power'] = df['Rad'] * 11.4 * 0.001
        return df
    except Exception as e:
        st.error(f"Помилка: {e}")
        return pd.DataFrame()

df = get_data()

# 2. Пряма перевірка
if not df.empty:
    st.success("Дані отримано успішно!")
    
    # Створюємо графік найпростішим способом
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['Time'], 
        y=df['Power'], 
        mode='lines+markers', # Додав точки, щоб було видно навіть поодинокі дані
        name="Прогноз",
        line=dict(color='red', width=3)
    ))

    fig.update_layout(
        height=500,
        margin=dict(l=20, r=20, t=20, b=20),
        xaxis_title="Час",
        yaxis_title="МВт"
    )

    # Використовуємо спрощений виклик
    st.plotly_chart(fig, use_container_width=True, theme=None)
    
    st.write("### Технічна таблиця (контроль):")
    st.dataframe(df.head(10))
else:
    st.warning("Таблиця порожня. Перевірте WEATHER_API_KEY у Secrets.")
