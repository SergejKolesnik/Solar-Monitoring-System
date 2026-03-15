import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time
import pytz

# 1. КОНФІГУРАЦІЯ
st.set_page_config(page_title="SkyGrid: Режим відновлення", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')

st.title("🚀 SkyGrid: Режим відновлення даних")
st.info("API погоди тимчасово вимкнено для обходу блокування. Відображаються лише дані АСКОЕ.")

# 2. ЗАВАНТАЖЕННЯ ДАНИХ З GITHUB
try:
    v_tag = int(time.time() / 60)
    repo_url = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={v_tag}"
    df_fact = pd.read_csv(repo_url)
    df_fact['Time'] = pd.to_datetime(df_fact['Time'])
    
    # Метрики
    last_date = df_fact['Time'].dt.date.max()
    days_count = len(df_fact['Time'].dt.date.unique())
    
    m1, m2 = st.columns(2)
    m1.metric("ОСТАННІ ДАНІ", last_date.strftime("%d.%m.%Y"))
    m2.metric("БАЗА НАПОВНЕНА", f"{days_count} днів")

    # Графік реальної генерації
    st.subheader("📊 Історія генерації (АСКОЕ)")
    fig = go.Figure()
    # Беремо останні 5 днів для наочності
    df_plot = df_fact.tail(120) 
    fig.add_trace(go.Scatter(x=df_plot['Time'], y=df_plot['Fact_MW'], 
                             name="Факт МВт", fill='tozeroy', 
                             line=dict(color='#ff4b4b', width=3)))
    fig.update_layout(height=400, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
    
    st.success("✅ База на GitHub працює справно. Collector виконав завдання.")

except Exception as e:
    st.error(f"Помилка завантаження бази: {e}")

st.markdown("---")
st.write("Спробуємо повернути прогноз погоди через годину, коли знімуть обмеження по IP.")
