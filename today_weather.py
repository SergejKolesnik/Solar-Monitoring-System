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

COMPACT_COLUMNS = (
    "Time",
    "temperature_2m",
    "cloud_cover",
    "shortwave_radiation",
    "precipitation",
    "wind_speed_10m",
    "weather_code",
)


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


def _format_compact_hourly_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the solar-focused hourly view shown by default."""

    compact = frame.loc[:, [column for column in COMPACT_COLUMNS if column in frame]].copy()
    compact["Час"] = compact.pop("Time").dt.strftime("%H:%M")
    compact["Стан"] = compact["weather_code"].map(WEATHER_CODES).fillna("—")
    compact = compact.drop(columns=["weather_code"])
    rename = {
        "temperature_2m": "Температура, °C",
        "cloud_cover": "Хмарність, %",
        "shortwave_radiation": "Радіація, Вт/м²",
        "precipitation": "Опади, мм",
        "wind_speed_10m": "Вітер, м/с",
    }
    return compact.rename(columns=rename).round(2)


def _render_kpi_cards(first: pd.Series) -> None:
    """Render a responsive KPI grid with solar metrics first."""

    def value(field: str, suffix: str = "", digits: int = 1) -> str:
        current = first.get(field)
        if pd.isna(current):
            return "—"
        return f"{current:.{digits}f}{suffix}"

    weather_code = first.get("weather_code")
    weather_label = (
        WEATHER_CODES.get(int(weather_code), "—")
        if pd.notna(weather_code)
        else "—"
    )
    cards = [
        ("☀️", "Радіація", value("shortwave_radiation", " Вт/м²", 0), "solar"),
        ("☁️", "Хмарність", value("cloud_cover", " %", 0), "solar"),
        ("🌡️", "Температура", value("temperature_2m", " °C"), "neutral"),
        ("↔️", "Відчувається", value("apparent_temperature", " °C"), "neutral"),
        ("💨", "Вітер", value("wind_speed_10m", " м/с"), "neutral"),
        ("☔", "Стан", weather_label, "neutral"),
    ]
    html = """<div class="weather-kpi-grid">{}\n</div>""".format(
        "".join(
            f'''<div class="weather-kpi {tone}">
                <div class="weather-kpi-label"><span>{icon}</span>{label}</div>
                <div class="weather-kpi-value">{display}</div>
            </div>'''
            for icon, label, display, tone in cards
        )
    )
    st.markdown(html, unsafe_allow_html=True)


def draw_today_weather_tab() -> None:
    """Render an isolated, read-only detailed weather tab."""

    st.markdown("### Погода сьогодні — погодинний прогноз")
    st.caption(
        "Open-Meteo, координати СЕС: 47.631494, 34.348690. "
        "Дані не записуються в Google Sheets і не впливають на модель."
    )
    if not st.session_state.get("today_weather_loaded", False):
        st.caption("Прогноз завантажується окремо й не додає запитів до основної моделі.")
        if not st.button("Завантажити прогноз на сьогодні", key="load_today_weather"):
            return
        st.session_state["today_weather_loaded"] = True

    action_columns = st.columns([1, 1, 2])
    if action_columns[0].button("Оновити", key="refresh_today_weather"):
        fetch_today_detailed_weather.clear()
    action_columns[1].caption("Оновлюється кожні 15 хв")

    frame = fetch_today_detailed_weather()
    if frame.empty:
        st.warning("Детальний прогноз тимчасово недоступний. Основні вкладки не змінені.")
        return

    first = frame.iloc[0]
    st.markdown(
        """
        <style>
        .weather-kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: .65rem; margin: .4rem 0 1rem; }
        .weather-kpi { background: #1e1e2e; border: 1px solid #343448; border-radius: 12px; padding: .75rem .85rem; min-height: 88px; }
        .weather-kpi.solar { border-color: #9b6d19; background: linear-gradient(145deg, #2a2519, #1e1e2e); }
        .weather-kpi-label { color: #a9acbd; font-size: .82rem; white-space: nowrap; }
        .weather-kpi-label span { margin-right: .35rem; }
        .weather-kpi-value { color: #f3f4f8; font-size: 1.35rem; font-weight: 700; margin-top: .45rem; white-space: nowrap; }
        @media (max-width: 900px) { .weather-kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
        @media (max-width: 520px) { .weather-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _render_kpi_cards(first)

    st.subheader("Погодинна картина для СЕС")
    st.plotly_chart(_build_weather_chart(frame), use_container_width=True)
    st.subheader("Коротка таблиця")
    st.dataframe(
        _format_compact_hourly_table(frame),
        use_container_width=True,
        hide_index=True,
    )
    with st.expander("Розширені параметри"):
        st.caption("Додаткові метеопараметри залишені доступними окремо, щоб не перевантажувати основний екран.")
        st.dataframe(_format_hourly_table(frame), use_container_width=True, hide_index=True)


def _build_weather_chart(frame: pd.DataFrame):
    """Build the chart lazily so importing the module stays lightweight."""

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        row_heights=[0.62, 0.38],
        specs=[[{"secondary_y": True}], [{"secondary_y": True}]],
    )
    figure.add_trace(
        go.Scatter(
            x=frame["Time"], y=frame["shortwave_radiation"],
            name="Радіація, Вт/м²", mode="lines",
            line=dict(color="#ffb800", width=3), fill="tozeroy",
            fillcolor="rgba(255,184,0,.18)",
        ),
        row=1, col=1, secondary_y=False,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["Time"], y=frame["cloud_cover"],
            name="Хмарність, %", line=dict(color="#8d96aa", width=2, dash="dot"),
        ),
        row=1, col=1, secondary_y=True,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["Time"], y=frame["temperature_2m"],
            name="Температура, °C", line=dict(color="#f2f4f8", width=2),
        ),
        row=2, col=1, secondary_y=False,
    )
    figure.add_trace(
        go.Bar(
            x=frame["Time"], y=frame["precipitation"], name="Опади, мм",
            marker_color="#4da3d9", opacity=0.55,
        ),
        row=2, col=1, secondary_y=True,
    )
    figure.add_trace(
        go.Scatter(
            x=frame["Time"], y=frame["wind_speed_10m"],
            name="Вітер, м/с", line=dict(color="#69c0a8", width=2, dash="dash"),
        ),
        row=2, col=1, secondary_y=True,
    )
    figure.update_layout(
        height=520, margin=dict(l=0, r=0, t=20, b=0), hovermode="x unified",
        legend=dict(orientation="h", y=1.08),
    )
    figure.update_yaxes(title_text="Вт/м²", row=1, col=1, secondary_y=False)
    figure.update_yaxes(title_text="%", row=1, col=1, secondary_y=True)
    figure.update_yaxes(title_text="°C", row=2, col=1, secondary_y=False)
    figure.update_yaxes(title_text="м/с / мм", row=2, col=1, secondary_y=True)
    return figure
