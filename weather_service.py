import streamlit as st
import pandas as pd
import requests
import time

# Visual Crossing повертає LOCAL time для заданих координат.
# Для Нiкополя (UTC+3) час вже є київським -- конвертація НЕ потрiбна.

@st.cache_data(ttl=600)
def fetch_weather_data():
    try:
        if "WEATHER_API_KEY" not in st.secrets:
            st.error("Ключ WEATHER_API_KEY не знайдено в Secrets!")
            return pd.DataFrame()
        api_key = st.secrets["WEATHER_API_KEY"]
        url = (
            f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/"
            f"47.631494,34.348690/next10days"
            f"?unitGroup=metric"
            f"&elements=datetime,temp,solarradiation,cloudcover,windspeed,precipprob"
            f"&key={api_key}"
            f"&contentType=json"
            f"&t={int(time.time())}"
        )
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            h_list = []
            for d in data['days']:
                for hr in d['hours']:
                    h_list.append({
                        'Time': pd.to_datetime(f"{d['datetime']} {hr['datetime']}"),
                        'Rad': float(hr.get('solarradiation', 0)),
                        'Temp': float(hr.get('temp', 0)),
                        'CloudCover': float(hr.get('cloudcover', 0)),
                        'WindSpeed': float(hr.get('windspeed', 0)),
                        'PrecipProb': float(hr.get('precipprob', 0)),
                    })
            df = pd.DataFrame(h_list)
            # Forecast_MW НЕ рахуємо тут -- це робиться в app.py через calc_forecast_mw()
            return df
        else:
            st.error(f"Помилка API: Статус {res.status_code}")
    except Exception as e:
        st.error(f"Помилка у weather_service: {e}")
    return pd.DataFrame()


def calc_site_kef(df_h):
    """Розраховує коефiцiєнт k = Fact_MW / (Rad_est * Capacity_MW).
    Виключає фiзично неможливi записи (Fact > 110% Capacity).
    """
    OLD_CONST = 0.0114
    DEFAULT_KEF = OLD_CONST / 12.5  # ~0.000912

    try:
        df = df_h.copy()
        df['Fact_MW'] = pd.to_numeric(
            df['Fact_MW'].astype(str).str.replace(',', '.'), errors='coerce'
        ).fillna(0)
        df['Forecast_MW'] = pd.to_numeric(
            df['Forecast_MW'].astype(str).str.replace(',', '.'), errors='coerce'
        ).fillna(0)
        df['Capacity_MW'] = pd.to_numeric(
            df['Capacity_MW'].astype(str).str.replace(',', '.'), errors='coerce'
        ).fillna(12.5)

        # Тiльки записи де всi значення є, без фiзичних аномалiй
        mask = (
            (df['Forecast_MW'] > 0.05) &
            (df['Fact_MW'] > 0.05) &
            (df['Capacity_MW'] > 0) &
            (df['Fact_MW'] <= df['Capacity_MW'] * 1.1)
        )
        df_clean = df[mask].copy()

        if len(df_clean) < 20:
            return DEFAULT_KEF

        df_clean['k'] = df_clean['Fact_MW'] / (
            df_clean['Forecast_MW'] / OLD_CONST * df_clean['Capacity_MW']
        )

        q_low = df_clean['k'].quantile(0.05)
        q_high = df_clean['k'].quantile(0.95)
        df_trim = df_clean[(df_clean['k'] >= q_low) & (df_clean['k'] <= q_high)]

        kef = float(df_trim['k'].median())

        # Захист: kef має бути в розумних межах
        if kef <= 0 or kef > 0.005:
            return DEFAULT_KEF

        return round(kef, 6)

    except Exception:
        return DEFAULT_KEF


def calc_forecast_mw(df_f, capacity_mw, kef):
    """Forecast_MW = Rad * capacity_mw * kef."""
    df = df_f.copy()
    df['Forecast_MW'] = (df['Rad'] * capacity_mw * kef).round(3)
    df['Forecast_MW'] = df['Forecast_MW'].clip(lower=0)
    return df
