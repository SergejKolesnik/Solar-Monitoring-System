import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime

st.set_page_config(page_title="СЕС Нікополь 11.4 МВт", layout="wide")

# --- ФУНКЦІЯ ПРОГНОЗУ (v2.6) ---
def get_weather_forecast():
    # Координати Нікополя
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloudrate&timezone=auto"
    data = requests.get(url).json()
    hourly = data['hourly']
    df = pd.DataFrame({
        'Час': pd.to_datetime(hourly['time']),
        'Радіація': hourly['shortwave_radiation'],
        'Хмарність': hourly['cloudrate']
    })
    # Наша модель v2.6: враховуємо Bifacial та 11.4 МВт (К=0.00092 для піків)
    df['Прогноз_МВт'] = df['Радіація'] * 11.4 * 0.00092 * (1 - df['Хмарність']/100 * 0.5)
    df.loc[df['Прогноз_МВт'] < 0, 'Прогноз_МВт'] = 0
    return df

st.title("☀️ Система прогнозування СЕС Нікополь")
st.markdown("### Потужність: 11.4 МВт | Режим: Live Прогноз")

# Отримуємо свіжий прогноз з інтернету
with st.spinner('Оновлення прогнозу погоди...'):
    df_forecast = get_weather_forecast()
    current_day = df_forecast[df_forecast['Час'].dt.date == datetime.now().date()]

# Спроба завантажити ФАКТ від колектора
try:
    df_fact = pd.read_csv("solar_ai_base.csv")
    st.success("✅ Дані АСКОЕ синхронізовано")
except:
    df_fact = None
    st.info("ℹ️ Очікуємо дані АСКОЕ з пошти (поки відображаємо тільки прогноз)")

# Вивід метрик
col1, col2 = st.columns(2)
with col1:
    today_gen = current_day['Прогноз_МВт'].sum()
    st.metric("Очікувана генерація (доба)", f"{today_gen:.2f} МВт*год")
with col2:
    if df_fact is not None:
        fact_gen = df_fact['Факт_МВт'].sum()
        st.metric("Реальна генерація (АСКОЕ)", f"{fact_gen:.2f} МВт*год")
    else:
        st.metric("Реальна генерація (АСКОЕ)", "Синхронізація...")

# Графік
st.subheader("📊 Графік генерації на сьогодні")
fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(current_day['Час'], current_day['Прогноз_МВт'], color='gold', label='Прогноз v2.6', linewidth=3)
ax.fill_between(current_day['Час'], current_day['Прогноз_МВт'], color='gold', alpha=0.1)

if df_fact is not None:
    # Додаємо лінію факту, якщо файл прийшов
    ax.step(df_fact['Час'], df_fact['Факт_МВт'], color='red', label='Факт АСКОЕ', where='post')

ax.legend()
ax.grid(True, alpha=0.3)
st.pyplot(fig)
