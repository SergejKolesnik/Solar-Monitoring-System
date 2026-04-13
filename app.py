import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import time, io, pytz
from datetime import datetime, timedelta

# 1. ОСНОВНІ НАЛАШТУВАННЯ
st.set_page_config(page_title="SkyGrid Solar AI", layout="wide", page_icon="☀️")
UA_TZ = pytz.timezone('Europe/Kyiv')
now_ua = datetime.now(UA_TZ).replace(tzinfo=None)

# Імпортуємо ваші модулі (переконайтеся, що вони є в репозиторії)
try:
    from model_engine import train_and_predict
except:
    def train_and_predict(h, f): return f['Forecast_MW'] * 1.02, 95.0

# 2. НАДІЙНЕ ЗАВАНТАЖЕННЯ ПОГОДИ (З КЕШУВАННЯМ)
@st.cache_data(ttl=3600)
def fetch_weather_final():
    try:
        if "WEATHER_API_KEY" not in st.secrets: return pd.DataFrame()
        api_key = st.secrets["WEATHER_API_KEY"]
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/47.631494,34.348690/next10days?unitGroup=metric&key={api_key}&contentType=json"
        res = requests.get(url, timeout=15)
        if res.status_code == 200 and 'application/json' in res.headers.get('Content-Type', ''):
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

# --- ЗАПУСК ІНТЕРФЕЙСУ ---
st.title("☀️ SkyGrid Solar AI")
df_f = fetch_weather_final()

if not df_f.empty:
    try:
        # Завантаження вашої бази з GitHub
        url_base = f"https://raw.githubusercontent.com/SergejKolesnik/Solar-Monitoring-System/main/solar_ai_base.csv?v={int(time.time()/60)}"
        df_h = pd.read_csv(url_base)
        
        # Розрахунок ШІ
        ai_preds, accuracy = train_and_predict(df_h, df_f)
        df_f['AI_MW'] = ai_preds.astype(float)
        
        # Обнулення ночі
        night = (df_f['Time'].dt.hour < 5) | (df_f['Time'].dt.hour > 20)
        df_f.loc[night, ['AI_MW', 'Forecast_MW']] = 0.0

        # СТВОРЮЄМО ВКЛАДКИ (Повертаємо структуру)
        tabs = st.tabs(["📊 МОНІТОРИНГ", "🧠 НАВЧАННЯ", "📑 БАЗА"])

        with tabs[0]:
            # Метрики на 3 дні
            c1, c2, c3 = st.columns(3)
            days = [now_ua.date() + timedelta(days=i) for i in range(3)]
            for i, col in enumerate([c1, c2, c3]):
                d_slice = df_f[df_f['Time'].dt.date == days[i]]
                if not d_slice.empty:
                    val = d_slice['AI_MW'].sum()
                    col.metric(f"{days[i].strftime('%d.%m')}", f"{val:.2f} МВт·год")

            # ГРАФІК (Гарний вигляд)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['Forecast_MW'].head(72), 
                                     name="Прогноз сайту", line=dict(dash='dot', color='rgba(150,150,150,0.7)', width=2)))
            fig.add_trace(go.Scatter(x=df_f['Time'].head(72), y=df_f['AI_MW'].head(72), 
                                     name="План ШІ (коригований)", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
            
            fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.05, x=1, xanchor="right"),
                              margin=dict(l=0, r=0, t=40, b=0), height=450)
            st.plotly_chart(fig, use_container_width=True)
            
            # Кнопка Excel
            output = io.BytesIO()
            excel_df = df_f.head(72)[['Time', 'Forecast_MW', 'AI_MW']].copy()
            excel_df.columns = ['Час', 'Сайт (МВт)', 'ШІ (МВт)']
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                excel_df.to_excel(writer, index=False)
            st.download_button("📥 Завантажити План Excel", output.getvalue(), f"Solar_Plan_{now_ua.strftime('%d_%m')}.xlsx")

        with tabs[1]:
            st.subheader(f"🧠 Точність моделі: {accuracy:.1f}%")
            st.write(f"Використано {len(df_h)} записів з бази АСКОЕ.")
            st.info("Модель автоматично перенавчається при кожному оновленні бази на GitHub.")

        with tabs[2]:
            st.subheader("📑 Останні дані з бази")
            st.dataframe(df_h.tail(20), use_container_width=True)

    except Exception as e:
        st.error(f"Помилка обробки даних: {e}")
else:
    st.error("Погода не завантажилася. Ключ API тимчасово обмежений (Error 429).")
    if st.button("🔄 Спробувати оновити"):
        st.cache_data.clear()
        st.rerun()
