import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
import time, pytz
# Імпортуємо наш новий блок навчання
from model_engine import train_and_predict

st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

@st.cache_data(ttl=3600)
def get_data():
    # Завантаження метео та бази
    # (код fetch_weather та читання CSV залишається базовим)
    # ... (я пропущу частину з API для стислості) ...
    return df_f, df_h

df_f, df_h = get_data() # Отримуємо дані

if df_f is not None and not df_h.empty:
    # ВИКЛИК БЛОКУ НАВЧАННЯ
    ai_predictions, accuracy = train_and_predict(df_h, df_f)
    df_f['AI_MW'] = ai_predictions
    # Обнуляємо ніч
    df_f.loc[(df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20), 'AI_MW'] = 0
    
    # Далі йде тільки відображення (Tabs, Plotly)
    st.title(f"☀️ SkyGrid AI (Точність: {accuracy:.1f}%)")
    # ... (код графіків) ...
