import streamlit as st
import pandas as pd
import requests
import time

@st.cache_data(ttl=600)
def fetch_weather_data():
    try:
        if "WEATHER_API_KEY" not in st.secrets:
            st.error("Ключ WEATHER_API_KEY не знайдено в Secrets!")
            return pd.DataFrame()
            
        api_key = st.secrets["WEATHER_API_KEY"]
        # Додаємо t={time.time()}, щоб обійти кешування на рівні запиту
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,solarradiation&key={api_key}&contentType=json&t={int(time.time())}"
        
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': float(hr.get('solarradiation', 0)),
                        'Temp': float(hr.get('temp', 0))
                    })
            df = pd.DataFrame(h_list)
            # Створюємо базову колонку прогнозу сайту
            df['Forecast_MW'] = (df['Rad'] * 11.4 * 0.001).astype(float)
            return df
        else:
            st.error(f"Помилка API: Статус {res.status_code}")
    except Exception as e:
        st.error(f"Помилка у weather_service: {e}")
    return pd.DataFrame()
