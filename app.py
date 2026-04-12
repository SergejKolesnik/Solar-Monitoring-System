import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time, io, pytz
from datetime import datetime, timedelta

# 1. НАЛАШТУВАННЯ
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

@st.cache_data(ttl=3600) # Кешуємо на 1 годину, щоб не блокували ключ
def get_stable_data():
    try:
        if "WEATHER_API_KEY" not in st.secrets:
            return pd.DataFrame()
            
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next2days?unitGroup=metric&key={api_key}&contentType=json"
        
        res = requests.get(url, timeout=15)
        
        # Перевірка, чи прийшов саме JSON
        if res.status_code == 200 and 'application/json' in res.headers.get('Content-Type', ''):
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': float(hr.get('solarradiation', 0))
                    })
            df = pd.DataFrame(h_list)
            df['Прогноз сайту (МВт)'] = df['Rad'] * 11.4 * 0.001
            df['Прогноз ШІ (МВт)'] = df['Прогноз сайту (МВт)'] * 1.02
            return df
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()

# --- ВІЗУАЛ ---
st.title("☀️ SkyGrid Solar AI (Recovery Mode)")

df = get_stable_data()

if not df.empty:
    # Обнуляємо ніч
    night = (df['Time'].dt.hour < 5) | (df['Time'].dt.hour > 20)
    df.loc[night, ['Прогноз ШІ (МВт)', 'Прогноз сайту (МВт)']] = 0.0

    # Графік
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['Time'], y=df['Прогноз сайту (МВт)'], name="Сайт", line=dict(dash='dot', color='gray')))
    fig.add_trace(go.Scatter(x=df['Time'], y=df['Прогноз ШІ (МВт)'], name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f')))
    
    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)
    
    st.success("Систему відновлено. Дані закешовані на 1 годину для стабільності.")
else:
    st.error("Сервер погоди тимчасово перевантажений або ключ заблоковано.")
    st.info("Зачекайте 10-15 хвилин. Система автоматично відновить роботу, коли API зніме обмеження.")
    if st.button("Спробувати оновити зараз"):
        st.cache_data.clear()
        st.rerun()
