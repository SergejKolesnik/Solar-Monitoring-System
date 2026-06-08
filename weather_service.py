import streamlit as st
import pandas as pd
import requests
import time

@st.cache_data(ttl=600)
def fetch_weather_data():
        """Завантажує погодні дані з Visual Crossing.
            Повертає сиру радіацію (Rad) — без Forecast_MW,
                бо він залежить від capacity_mw яку обирає користувач."""
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
            # Forecast_MW НЕ рахуємо тут — це робиться в app.py через calc_forecast_mw()
            return df

else:
            st.error(f"Помилка API: Статус {res.status_code}")

except Exception as e:
        st.error(f"Помилка у weather_service: {e}")

    return pd.DataFrame()


def calc_site_kef(df_h: pd.DataFrame) -> float:
        """Розраховує питомий коефіцієнт k = Fact_MW / (Rad * Capacity_MW)
            на основі наявних фактичних даних у базі.

                Логіка:
                      - Беремо тільки денні години де є і факт і радіація (> 0)
                            - Для кожного запису рахуємо k = Fact_MW / (Rad * Capacity_MW)
                                  - Беремо медіану — стійка до викидів (хмарні дні, часткова тінь тощо)
                                        - Якщо даних мало або щось пішло не так — повертаємо дефолт 0.00091
                                                (відповідає приблизно 11.4 кВт / 12.5 МВт * корекція = ~0.00091)
                                                    """
    DEFAULT_KEF = 0.00091  # запасний коефіцієнт якщо бракує даних

    try:
                df = df_h.copy()
        df['Rad'] = pd.to_numeric(df['Rad'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        df['Fact_MW'] = pd.to_numeric(df['Fact_MW'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
        df['Capacity_MW'] = pd.to_numeric(df['Capacity_MW'].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)

        # Тільки записи де є всі три значення > 0
        mask = (df['Rad'] > 10) & (df['Fact_MW'] > 0) & (df['Capacity_MW'] > 0)
        df_clean = df[mask].copy()

        if len(df_clean) < 20:
                        return DEFAULT_KEF

        df_clean['k'] = df_clean['Fact_MW'] / (df_clean['Rad'] * df_clean['Capacity_MW'])

        # Відкидаємо явні аномалії (нижні 5% та верхні 5%)
        q_low = df_clean['k'].quantile(0.05)
        q_high = df_clean['k'].quantile(0.95)
        df_trim = df_clean[(df_clean['k'] >= q_low) & (df_clean['k'] <= q_high)]

        kef = float(df_trim['k'].median())

        if kef <= 0 or kef > 0.01:  # захист від аномальних значень
                        return DEFAULT_KEF

        return round(kef, 6)

except Exception:
        return DEFAULT_KEF


def calc_forecast_mw(df_f: pd.DataFrame, capacity_mw: float, kef: float) -> pd.DataFrame:
        """Розраховує Forecast_MW для df_f на основі радіації, потужності СЕС і коефіцієнта.

            Forecast_MW = Rad * capacity_mw * kef

                Викликається в app.py після вибору capacity_mw користувачем,
                    тому завжди відповідає поточній потужності СЕС.
                        """
    df = df_f.copy()
    df['Forecast_MW'] = (df['Rad'] * capacity_mw * kef).round(3)
    df['Forecast_MW'] = df['Forecast_MW'].clip(lower=0)
    return df
