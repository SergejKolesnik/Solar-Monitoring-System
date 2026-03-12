import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime

st.set_page_config(page_title="СЕС Нікополь 11.4 МВт", layout="wide")

# --- ФУНКЦІЯ ПРОГНОЗУ (v2.6) ---
def get_weather_forecast():
    # Стабільне посилання з усіма параметрами
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover&timezone=auto"
    try:
        response = requests.get(url)
        data = response.json()
        
        if 'hourly' not in data:
            st.error(f"Помилка метеосервісу: {data.get('reason', 'Невідома помилка')}")
            return None
            
        hourly = data['hourly']
        df = pd.DataFrame({
            'Час': pd.to_datetime(hourly['time']),
            'Радіація': hourly['shortwave_radiation'],
            'Хмарність': hourly['cloud_cover']
        })
        # Наша модель v2.6 для Нікополя (11.4 МВт)
        df['Прогноз_МВт'] = df['Радіація'] * 11.4 * 0.00092 * (1 - df['Хмарність']/100 * 0.4)
        df.loc[df['Прогноз_МВт'] < 0, 'Прогноз_МВт'] = 0
        return df
    except Exception as e:
        st.error(f"Помилка підключення: {e}")
        return None

st.title("☀️ Система прогнозування СЕС Нікополь")
st.markdown("### Потужність: 11.4 МВт | Режим: Live Прогноз")

# Отримуємо свіжий прогноз
df_forecast = get_weather_forecast()

if df_forecast is not None:
    current_day = df_forecast[df_forecast['Час'].dt.date == datetime.now().date()]
    
    # Вивід метрик
    col1, col2 = st.columns(2)
    with col1:
        today_gen = current_day['Прогноз_МВт'].sum()
        st.metric("Очікувана генерація (доба)", f"{today_gen:.2f} МВт*год")
    with col2:
        st.metric("Статус системи", "Працює (Live)")

    # Графік
    st.subheader("📊 Графік генерації на сьогодні")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(current_day['Час'], current_day['Прогноз_МВт'], color='#FFD700', linewidth=3, label='Прогноз v2.6')
    ax.fill_between(current_day['Час'], current_day['Прогноз_МВт'], color='#FFD700', alpha=0.2)
    ax.set_ylabel("Потужність, МВт")
    ax.grid(True, alpha=0.2)
    st.pyplot(fig)
else:
    st.warning("🔄 Спробуйте оновити сторінку через хвилину. Метеосервіс тимчасово недоступний.")
