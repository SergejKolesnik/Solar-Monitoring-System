import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

# Налаштування сторінки
st.set_page_config(page_title="СЕС Нікополь 11.4 МВт", layout="wide")

st.title("☀️ Хмарний моніторинг СЕС Нікополь")
st.sidebar.info("Модель: v2.6 (Оптимізована під пік)")

# Функція завантаження даних
def load_data():
    try:
        # Сайт буде шукати файл, який пришле ваш домашній комп'ютер
        df = pd.read_csv("solar_ai_base.csv")
        return df
    except:
        return None

df = load_data()

if df is not None:
    # Головні показники (метрики)
    col1, col2 = st.columns(2)
    latest_power = df['Прогноз_МВт'].iloc[-1]
    
    with col1:
        st.metric("Прогноз зараз (МВт)", f"{latest_power:.2f}")
    with col2:
        st.metric("Статус ШІ", "Навчання на даних АСКОЕ")

    # Графік
    st.subheader("📊 Графік генерації")
    st.line_chart(df.set_index('Час')[['Прогноз_МВт']])
else:
    st.warning("⏱ Очікуємо синхронізації з локальним комп'ютером у Нікополі...")
    st.info("Як тільки файл 'solar_ai_base.csv' з'явиться в репозиторії, тут з'являться графіки.")
