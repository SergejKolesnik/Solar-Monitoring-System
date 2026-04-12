import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
from datetime import datetime, timedelta
import time, pytz
# Імпортуємо наш новий файл
from model_engine import train_and_predict

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid Solar AI v20.0", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

# ... (тут залишається ваш код fetch_weather) ...

df_f, day_forecast = fetch_weather()
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 2. ЗАВАНТАЖЕННЯ ДАНИХ ТА ВИКЛИК ШІ
try:
    v = int(time.time() / 60)
    url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v}"
    df_h = pd.read_csv(url)
    df_h['Time'] = pd.to_datetime(df_h['Time'])
    
    if df_f is not None:
        # Викликаємо функцію з нашого нового файлу
        ai_preds, model_acc = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds
        # Обнуляємо нічні години (з 21:00 до 05:00)
        df_f.loc[(df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20), 'AI_MW'] = 0
except:
    df_h, model_acc = pd.DataFrame(), 0

# 3. ІНТЕРФЕЙС (Tabs)
st.title(f"☀️ SkyGrid Solar AI (Точність: {model_acc:.1f}%)")
# ... (код вкладок Моніторинг, Метео, База) ...
