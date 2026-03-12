import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="СЕС Нікополь 11.4 МВт", layout="wide")

def get_weather_forecast():
    # Запитуємо прогноз на 3 дні
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover&timezone=auto&forecast_days=3"
    try:
        response = requests.get(url)
        data = response.json()
        if 'hourly' not in data: return None
            
        hourly = data['hourly']
        df = pd.DataFrame({
            'Час': pd.to_datetime(hourly['time']),
            'Радіація': hourly['shortwave_radiation'],
            'Хмарність': hourly['cloud_cover']
        })
        # Модель v2.6 (11.4 МВт)
        df['Прогноз_МВт'] = df['Радіація'] * 11.4 * 0.00092 * (1 - df['Хмарність']/100 * 0.4)
        df.loc[df['Прогноз_МВт'] < 0, 'Прогноз_МВт'] = 0
        return df
    except:
        return None

# Дати для заголовка
start_date = datetime.now().strftime("%d.%m")
end_date = (datetime.now() + timedelta(days=2)).strftime("%d.%m")

st.title(f"☀️ Прогноз СЕС Нікополь ({start_date} — {end_date})")
st.markdown("### Потужність: 11.4 МВт | Режим: Трьохденний моніторинг")

df_forecast = get_weather_forecast()

if df_forecast is not None:
    # Метрики на сьогодні
    today_df = df_forecast[df_forecast['Час'].dt.date == datetime.now().date()]
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Сьогодні (МВт*год)", f"{today_df['Прогноз_МВт'].sum():.1f}")
    with col2:
        next_day = df_forecast[df_forecast['Час'].dt.date == (datetime.now() + timedelta(days=1)).date()]
        st.metric("Завтра (МВт*год)", f"{next_day['Прогноз_МВт'].sum():.1f}")
    with col3:
        st.metric("Статус", "Live Update")

    # Графік
    st.subheader("📊 Детальний графік генерації")
    
    # Налаштування розміру, щоб все "влізло"
    fig, ax = plt.subplots(figsize=(12, 4)) 
    ax.plot(df_forecast['Час'], df_forecast['Прогноз_МВт'], color='#FFD700', linewidth=2, label='Прогноз v2.6')
    ax.fill_between(df_forecast['Час'], df_forecast['Прогноз_МВт'], color='#FFD700', alpha=0.15)
    
    # Робимо сітку і підписи гарними
    ax.set_ylabel("МВт")
    ax.grid(True, linestyle='--', alpha=0.5)
    plt.xticks(rotation=0) # Горизонтальні підписи дат
    
    # Прибираємо зайві поля навколо графіка
    plt.tight_layout()
    
    st.pyplot(fig)
else:
    st.warning("Оновлюємо дані...")
