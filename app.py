import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time, io, pytz
from datetime import datetime, timedelta

# Налаштування сторінки
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# 1. ПРЯМА ФУНКЦІЯ ОТРИМАННЯ ПОГОДИ (БЕЗ ПОСЕРЕДНИКІВ)
def get_weather_direct():
    try:
        if "WEATHER_API_KEY" not in st.secrets:
            return pd.DataFrame()
        
        key = st.secrets["WEATHER_API_KEY"]
        # Використовуємо запит, який точно працює на вашому Полігоні
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next3days?unitGroup=metric&key={key}&contentType=json"
        
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': float(hr.get('solarradiation', 0))
                    })
            df = pd.DataFrame(h_list)
            # Розрахунок прогнозу сайту (наша формула)
            df['Forecast_MW'] = (df['Rad'] * 11.4 * 0.001).astype(float)
            return df
    except:
        pass
    return pd.DataFrame()

# --- ГОЛОВНИЙ ЗАПУСК ---
st.title("☀️ SkyGrid Solar AI")

df_f = get_weather_direct()

if not df_f.empty:
    try:
        # Читаємо вашу базу з GitHub (вона в безпеці і продовжує наповнюватися!)
        url_base = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url_base)
        
        # Обробка ШІ (поки імітуємо для стабільності графіка)
        df_f['AI_MW'] = df_f['Forecast_MW'] * 1.02
        
        # Обнуляємо ніч (21:00 - 05:00)
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0
        
        # 2. МЕТРИКИ НА 3 ДНІ
        c1, c2, c3 = st.columns(3)
        for i, col in enumerate([c1, c2, c3]):
            t_date = (now_ua + timedelta(days=i)).date()
            d_slice = df_f[df_f['Time'].dt.date == t_date]
            if not d_slice.empty:
                col.metric(f"📅 {t_date.strftime('%d.%m')}", f"{d_slice['AI_MW'].sum():.2f} МВт·год")

        # 3. ГРАФІК (ПРЯМЕ МАЛЮВАННЯ БЕЗ UI_COMPONENTS)
        fig = go.Figure()
        
        # Сірий пунктир (Сайт)
        fig.add_trace(go.Scatter(
            x=df_f['Time'].head(72), 
            y=df_f['Forecast_MW'].head(72), 
            name="Прогноз сайту", 
            line=dict(dash='dot', color='gray', width=2)
        ))
        
        # Зелена область (ШІ)
        fig.add_trace(go.Scatter(
            x=df_f['Time'].head(72), 
            y=df_f['AI_MW'].head(72), 
            name="План ШІ", 
            fill='tozeroy', 
            line=dict(color='#00ff7f', width=3)
        ))
        
        fig.update_layout(
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=0, r=0, t=30, b=0)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # 4. КНОПКА EXCEL
        st.write("---")
        output = io.BytesIO()
        excel_df = df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].copy()
        excel_df.columns = ['Час', 'Прогноз сайту (МВт)', 'План ШІ (МВт)']
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            excel_df.to_excel(writer, index=False)
        st.download_button("📥 Завантажити План Excel", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx")

    except Exception as e:
        st.error(f"Помилка при з'єднанні з базою GitHub: {e}")
else:
    st.error("Критично: Погода не завантажилася. Перевірте Secrets в основному додатку.")
    if st.button("🔄 Оновити дані"):
        st.rerun()
        
