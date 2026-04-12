import streamlit as st
import pandas as pd
import requests

@st.cache_data(ttl=3600)
def fetch_weather_data():
    try:
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,windspeed,precipprob&key={api_key}&contentType=json"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': hr.get('solarradiation', 0),
                        'CloudCover': hr.get('cloudcover', 0),
                        'Temp': hr.get('temp', 0),
                        'WindSpeed': hr.get('windspeed', 0),
                        'PrecipProb': hr.get('precipprob', 0)
                    })
            df = pd.DataFrame(h_list)
            df['Hour'] = df['Time'].dt.hour
            # Базовий прогноз (Сайт)
            df['Forecast_MW'] = (df['Rad'] * 11.4 * 0.001).round(3)
            return df
    except: pass
    return pd.DataFrame()
