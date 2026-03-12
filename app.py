import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime, timedelta

st.set_page_config(page_title="СЕС Нікополь 11.4 МВт", layout="wide")

def get_weather_data():
    # Запитуємо прогноз на 3 дні: радіація, хмарність, температура
    url = "https://api.open-meteo.com/v1/forecast?latitude=47.56&longitude=34.39&hourly=shortwave_radiation,cloud_cover,temperature_2m&timezone=auto&forecast_days=3"
    try:
        response = requests.get(url)
        data = response.json()
        if 'hourly' not in data: return None
            
        hourly = data['hourly']
        df = pd.DataFrame({
            'Час': pd.to_datetime(hourly['time']),
            'Радіація': hourly['shortwave_radiation'],
            'Хмарність': hourly['cloud_cover'],
            'Температура': hourly['temperature_2m']
        })
        # Модель v2.6 (11.4 МВт)
        df['Прогноз_МВт'] = df['Радіація'] * 11.4 * 0.00092 * (1 - df['Хмарність']/100 * 0.4)
        df.loc[df['Прогноз_МВт'] < 0, 'Прогноз_МВт'] = 0
        return df
    except:
        return None

# Формуємо заголовок з датами
start_d = datetime.now().strftime("%d.%m")
end_d = (datetime.now() + timedelta(days=2)).strftime("%d.%m")

st.title(f"☀️ Моніторинг СЕС Нікополь ({start_d} — {end_d})")

df = get_weather_data()

if df is not None:
    # Метрики у верхньому рядку
    today_df = df[df['Час'].dt.date == datetime.now().date()]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Сьогодні (МВт*год)", f"{today_df['Прогноз_МВт'].sum():.1f}")
    with c2:
        st.metric("Пік сьогодні (МВт)", f"{today_df['Прогноз_МВт'].max():.2f}")
    with c3:
        curr_temp = today_df.iloc[datetime.now().hour]['Температура']
        st.metric("Температура зараз", f"{curr_temp}°C")

    # Графік
    st.subheader("📊 Генерація, Хмарність та Температура")
    
    fig, ax1 = plt.subplots(figsize=(12, 5))

    # 1. Хмарність (сіра заливка на задньому фоні)
    ax1.fill_between(df['Час'], df['Хмарність'], color='gray', alpha=0.15, label='Хмарність %')
    
    # 2. Прогноз генерації (золота лінія)
    ax1.plot(df['Час'], df['Прогноз_МВт'], color='#FFD700', linewidth=3, label='Генерація МВт')
    ax1.fill_between(df['Час'], df['Прогноз_МВт'], color='#FFD700', alpha=0.2)
    ax1.set_ylabel("Потужність (МВт) / Хмарність (%)", fontsize=10)
    
    # 3. Тренд температури (червона пунктирна лінія на другій осі)
    ax2 = ax1.twinx()
    ax2.plot(df['Час'], df['Температура'], color='red', linestyle='--', linewidth=1.5, alpha=0.6, label='Температура °C')
    ax2.set_ylabel("Температура (°C)", color='red', fontsize=10)
    ax2.tick_params(axis='y', labelcolor='red')

    # Налаштування вигляду
    ax1.grid(True, linestyle=':', alpha=0.4)
    fig.legend(loc='upper right', bbox_to_anchor=(0.9, 0.88))
    plt.tight_layout()
    
    st.pyplot(fig)
    
    # Додаткова таблиця для перевірки
    with st.expander("Подивитися таблицю даних"):
        st.dataframe(df[['Час', 'Прогноз_МВт', 'Хмарність', 'Температура']].tail(10))
else:
    st.error("Помилка отримання даних. Перевірте з'єднання.")
