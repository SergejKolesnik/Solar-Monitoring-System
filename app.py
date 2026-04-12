import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time, io, pytz
from datetime import datetime, timedelta

# Налаштування
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 1. ФУНКЦІЯ ОТРИМАННЯ ПОГОДИ (ЯК НА ПОЛІГОНІ)
def get_weather_direct():
    try:
        if "WEATHER_API_KEY" not in st.secrets:
            return pd.DataFrame()
        
        key = st.secrets["WEATHER_API_KEY"]
        # Використовуємо запит як на працюючому Полігоні
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next3days?unitGroup=metric&key={key}&contentType=json"
        
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
            df['Forecast_MW'] = (df['Rad'] * 11.4 * 0.001).astype(float)
            return df
    except: pass
    return pd.DataFrame()

# ЗАПУСК
st.title("☀️ SkyGrid Solar AI")
df_f = get_weather_direct()

if not df_f.empty:
    try:
        # Читаємо вашу базу (наповнення триває!)
        url_base = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url_base)
        
        # Імітуємо ШІ для стабільності (або викликаємо вашу модель)
        df_f['AI_MW'] = df_f['Forecast_MW'] * 1.05 # Тимчасове коригування
        
        # Обнуляємо ніч
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0
        
        # ГРАФІК (ПРЯМЕ МАЛЮВАННЯ)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), 
                                 name="Прогноз сайту", line=dict(dash='dot', color='gray')))
        fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['AI_MW'].head(72), 
                                 name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f')))
        
        fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
        
        # КНОПКА EXCEL
        output = io.BytesIO()
        excel_df = df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].copy()
        excel_df.columns = ['Час', 'Сайт (МВт)', 'ШІ (МВт)']
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            excel_df.to_excel(writer, index=False)
        st.download_button("📥 Завантажити План Excel", output.getvalue(), "Solar_Plan.xlsx")

    except Exception as e:
        st.error(f"Помилка бази: {e}")
else:
    st.error("Погода не завантажилась. Спробуйте натиснути кнопку нижче.")
    if st.button("Оновити дані"):
        st.rerun()
