import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime
import time
import pytz
import io

# Конфігурація
st.set_page_config(page_title="SkyGrid Solar AI v15.5", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

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
                    'Icon': d.get('icon')
                })
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"), 
                        'Rad': hr.get('solarradiation', 0), 
                        'Clouds': hr.get('cloudcover', 0), 
                        'Temp': hr.get('temp', 0), 
                        'WindSpd': hr.get('windspeed', 0)
                    })
            return pd.DataFrame(h_list), d_list, "OK"
        return None, None, "Error"
    except: return None, None, "Error"

df_f, day_forecast, status = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)
ai_bias, exp_hours = 1.0, 0
daily_stats = pd.DataFrame()
df_h_mar = pd.DataFrame()

try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_h = pd.read_csv(repo_url)
    df_h['Time'] = pd.to_datetime(df_h['Time'])
    if 'CloudCover' in df_h.columns: df_h = df_h.rename(columns={'CloudCover': 'Clouds'})
    
    # Фільтрація за березень 2026
    df_h_mar = df_h[(df_h['Time'].dt.year == 2026) & (df_h['Time'].dt.month == 3)].copy()
    exp_hours = len(df_h_mar.dropna(subset=['Fact_MW']))
    
    # Розрахунок коефіцієнта похибки за останні 72 записи
    df_v = df_h_mar.dropna(subset=['Fact_MW', 'Forecast_MW']).tail(72)
