import streamlit as st
import pandas as pd
import requests
import time

# Visual Crossing повертає LOCAL time для заданих координат.
# Для Нiкополя (UTC+3) час вже є київським -- конвертацiя НЕ потрiбна.

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
            return df
        else:
            st.error(f"Помилка API: Статус {res.status_code}")
    except Exception as e:
        st.error(f"Помилка у weather_service: {e}")
    return pd.DataFrame()


@st.cache_data(ttl=1800)
def fetch_open_meteo_data():
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=47.631494"
            "&longitude=34.348690"
            "&hourly=temperature_2m,shortwave_radiation,cloud_cover,wind_speed_10m,precipitation_probability"
            "&forecast_days=10"
            "&timezone=Europe%2FKyiv"
            "&wind_speed_unit=ms"
        )
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            st.warning(f"Open-Meteo недоступний: статус {res.status_code}")
            return pd.DataFrame()

        data = res.json()
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return pd.DataFrame()

        def hourly_series(name):
            values = hourly.get(name, [])
            if len(values) != len(times):
                values = [0] * len(times)
            return pd.to_numeric(values, errors="coerce")

        df = pd.DataFrame({
            "Time": pd.to_datetime(times),
            "Rad": hourly_series("shortwave_radiation"),
            "Temp": hourly_series("temperature_2m"),
            "CloudCover": hourly_series("cloud_cover"),
            "WindSpeed": hourly_series("wind_speed_10m"),
            "PrecipProb": hourly_series("precipitation_probability"),
        })
        return df.fillna(0)
    except Exception as e:
        st.warning(f"Open-Meteo не завантажився: {e}")
        return pd.DataFrame()


def calc_site_kef(df_h):
    """
    Розраховує коефiцiєнт k = Fact_MW / Forecast_MW.
    Forecast_MW у базi вже є в МВт (Rad * 0.0114).
    DEFAULT_KEF = 1.0 (нейтральний: прогноз ШI = прогноз сайту).
    """
    DEFAULT_KEF = 1.0

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

        mask = (
            (df['Forecast_MW'] > 0.05) &
            (df['Fact_MW'] > 0.05) &
            (df['Capacity_MW'] > 0) &
            (df['Fact_MW'] <= df['Capacity_MW'] * 1.1)
        )
        df_clean = df[mask].copy()

        if len(df_clean) < 20:
            return DEFAULT_KEF

        df_clean['k'] = df_clean['Fact_MW'] / df_clean['Forecast_MW']

        q_low = df_clean['k'].quantile(0.05)
        q_high = df_clean['k'].quantile(0.95)
        df_trim = df_clean[(df_clean['k'] >= q_low) & (df_clean['k'] <= q_high)]

        kef = float(df_trim['k'].median())

        if kef <= 0.3 or kef > 1.5:
            return DEFAULT_KEF

        return round(kef, 4)

    except Exception:
        return DEFAULT_KEF


def calc_forecast_mw(df_f, capacity_mw, kef):
    """
    Forecast_MW = Rad * 0.0114 * (capacity_mw / 12.5) * kef
    Масштабуємо базову формулу collector.py пiд поточну потужнiсть СЕС.
    """
    BASE_CAPACITY = 12.5
    BASE_CONST = 0.0114

    df = df_f.copy()
    df['Forecast_MW'] = (
        df['Rad'] * BASE_CONST * (capacity_mw / BASE_CAPACITY) * kef
    ).round(3)
    df['Forecast_MW'] = df['Forecast_MW'].clip(lower=0)
    return df
