"""Read-only detailed hourly weather view for the current Kyiv-local day.

This module is deliberately separate from the production collector and the
solar forecast calculations.  It reads Open-Meteo directly and only runs when
the user requests the dedicated Streamlit view.
"""

from __future__ import annotations

import requests
import pandas as pd
import streamlit as st


LATITUDE = 47.631494
LONGITUDE = 34.348690
TIMEZONE = "Europe/Kyiv"

HOURLY_FIELDS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,dew_point_2m,"
    "precipitation,rain,showers,snowfall,snow_depth,weather_code,"
    "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
    "pressure_msl,surface_pressure,wind_speed_10m,wind_direction_10m,"
    "wind_gusts_10m,uv_index,visibility,evapotranspiration,"
    "vapour_pressure_deficit,soil_temperature_0cm,soil_moisture_0_to_1cm,"
    "shortwave_radiation,direct_radiation,diffuse_radiation,"
    "direct_normal_irradiance,global_tilted_irradiance"
)

FIELD_LABELS = {
    "temperature_2m": ("Температура", "°C"),
    "apparent_temperature": ("Відчувається як", "°C"),
    "relative_humidity_2m": ("Відносна вологість", "%"),
    "dew_point_2m": ("Точка роси", "°C"),
    "precipitation": ("Опади", "мм"),
    "rain": ("Дощ", "мм"),
    "showers": ("Зливи", "мм"),
    "snowfall": ("Сніг", "см"),
    "snow_depth": ("Висота снігу", "м"),
    "weather_code": ("Код стану", ""),
    "cloud_cover": ("Хмарність", "%"),
    "cloud_cover_low": ("Низька хмарність", "%"),
    "cloud_cover_mid": ("Середня хмарність", "%"),
    "cloud_cover_high": ("Висока хмарність", "%"),
    "pressure_msl": ("Тиск на рівні моря", "гПа"),
    "surface_pressure": ("Тиск на поверхні", "гПа"),
    "wind_speed_10m": ("Швидкість вітру", "м/с"),
    "wind_direction_10m": ("Напрямок вітру", "°"),
    "wind_gusts_10m": ("Пориви вітру", "м/с"),
    "uv_index": ("UV-індекс", ""),
    "visibility": ("Видимість", "м"),
    "evapotranspiration": ("Евапотранспірація", "мм"),
    "vapour_pressure_deficit": ("Дефіцит тиску пари", "кПа"),
    "soil_temperature_0cm": ("Температура ґрунту", "°C"),
    "soil_moisture_0_to_1cm": ("Вологість ґрунту", "м³/м³"),
    "shortwave_radiation": ("Короткохвильова радіація", "Вт/м²"),
    "direct_radiation": ("Пряма радіація", "Вт/м²"),
    "diffuse_radiation": ("Розсіяна радіація", "Вт/м²"),
    "direct_normal_irradiance": ("Пряма нормальна радіація", "Вт/м²"),
    "global_tilted_irradiance": ("Радіація на похилу площину", "Вт/м²"),
}

WEATHER_CODES = {
    0: "Ясно",
    1: "Переважно ясно",
    2: "Мінлива хмарність",
    3: "Похмуро",
    45: "Туман",
    48: "Туман з інеєм",
    51: "Слабка мряка",
    53: "Мряка",
    55: "Сильна мряка",
    61: "Слабкий дощ",
    63: "Дощ",
    65: "Сильний дощ",
    71: "Слабкий сніг",
    73: "Сніг",
    75: "Сильний сніг",
    80: "Слабкі зливи",
    81: "Зливи",
    82: "Сильні зливи",
    95: "Гроза",
    96: "Гроза з градом",
    99: "Сильна гроза з градом",
}


@st.cache_data(ttl=900)
def fetch_today_detailed_weather() -> pd.DataFrame:
    """Fetch today's local hourly forecast without writing to project data."""

    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": HOURLY_FIELDS,
        "forecast_days": 1,
        "timezone": TIMEZONE,
        "wind_speed_unit": "ms",
    }
    # Keep the request explicit and separate from the production dataframe.
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast", params=params, timeout=10
        )
        response.raise_for_status()
        hourly = response.json().get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return pd.DataFrame()

        frame = pd.DataFrame({"Time": pd.to_datetime(times, errors="coerce")})
        for field in FIELD_LABELS:
            values = hourly.get(field, [])
            if len(values) != len(times):
                values = [None] * len(times)
            frame[field] = pd.to_numeric(values, errors="coerce")
        return frame.dropna(subset=["Time"]).reset_index(drop=True)
    except (requests.RequestException, ValueError, TypeError):
        return pd.DataFrame()


def _format_hourly_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a compact, human-readable copy for the data grid."""

    table = frame.copy()
    table["Час"] = table.pop("Time").dt.strftime("%H:%M")
    table["Стан"] = table["weather_code"].map(WEATHER_CODES).fillna("—")
    table = table.drop(columns=["weather_code"])
    rename = {field: f"{label}, {unit}" if unit else label
              for field, (label, unit) in FIELD_LABELS.items()}
    return table.rename(columns=rename).round(2)


def draw_today_weather_tab() -> None:
    """Render an isolated, read-only detailed weather tab."""

    st.markdown("### Погода сьогодні — погодинний прогноз")
    st.caption(
        "Open-Meteo, координати СЕС: 47.631494, 34.348690. "
        "Дані не записуються в Google Sheets і не впливають на модель."
    )
    if not st.session_state.get("today_weather_loaded", False):
        st.info("Прогноз завантажується окремою кнопкою, щоб не додавати запитів до основної моделі.")
        if not st.button("Завантажити прогноз на сьогодні", key="load_today_weather"):
            return
        st.session_state["today_weather_loaded"] = True

    if st.button("Оновити погодний прогноз", key="refresh_today_weather"):
        fetch_today_detailed_weather.clear()

    frame = fetch_today_detailed_weather()
    if frame.empty:
        st.warning("Детальний прогноз тимчасово недоступний. Основні вкладки не змінені.")
        return

    first = frame.iloc[0]
    metric_columns = st.columns(5)
    metric_columns[0].metric("Температура", f"{first['temperature_2m']:.1f} °C")
    metric_columns[1].metric("Відчувається", f"{first['apparent_temperature']:.1f} °C")
    metric_columns[2].metric("Хмарність", f"{first['cloud_cover']:.0f} %")
    metric_columns[3].metric("Вітер", f"{first['wind_speed_10m']:.1f} м/с")
    weather_code = first.get("weather_code")
    weather_label = WEATHER_CODES.get(int(weather_code), "—") if pd.notna(weather_code) else "—"
    metric_columns[4].metric("Стан", weather_label)

    st.plotly_chart(
        _build_weather_chart(frame),
        use_container_width=True,
    )
    st.dataframe(
        _format_hourly_table(frame),
        use_container_width=True,
        hide_index=True,
    )


def _build_weather_chart(frame: pd.DataFrame):
    """Build the chart lazily so importing the module stays lightweight."""

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    figure = make_subplots(specs=[[{"secondary_y": True}]])
    figure.add_trace(
        go.Scatter(x=frame["Time"], y=frame["temperature_2m"], name="Температура, °C"),
        secondary_y=False,
    )
    figure.add_trace(
        go.Bar(x=frame["Time"], y=frame["precipitation"], name="Опади, мм", opacity=0.45),
        secondary_y=True,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["Time"], y=frame["shortwave_radiation"],
            name="Радіація, Вт/м²", line=dict(color="#ffb800"),
        ),
        secondary_y=True,
    )
    figure.update_layout(height=340, margin=dict(l=0, r=0, t=20, b=0), hovermode="x unified")
    figure.update_yaxes(title_text="°C", secondary_y=False)
    figure.update_yaxes(title_text="мм / Вт/м²", secondary_y=True)
    return figure
