import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def draw_app_header(logo_url):
    st.markdown(
        f"""
        <style>
        div[data-testid="stTabBar"] {{
            border-bottom: 1px solid rgba(255,255,255,0.06);
            gap: 8px;
        }}
        div[data-testid="stTabBar"] button {{
            color: #64748b !important;
            font-weight: 650 !important;
            font-size: 14px !important;
            border: none !important;
            padding: 10px 14px !important;
        }}
        div[data-testid="stTabBar"] button[aria-selected="true"] {{
            color: #ffb800 !important;
            background: rgba(255,184,0,0.06) !important;
            border-bottom: 2px solid #ffb800 !important;
        }}
        div[data-testid="stTabBarHighlight"] {{
            background-color: #ffb800 !important;
        }}
        .app-shell-header {{
            background: linear-gradient(135deg, rgba(17,22,34,0.98) 0%, rgba(11,17,26,0.98) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 18px 22px;
            margin: 10px 0 18px;
            box-shadow: 0 18px 36px rgba(0,0,0,0.28);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
        }}
        .app-brand {{
            display: flex;
            align-items: center;
            gap: 14px;
            min-width: 0;
        }}
        .app-brand__mark {{
            width: 42px;
            height: 42px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(255,184,0,0.14);
            color: #ffb800;
            box-shadow: 0 0 24px rgba(255,184,0,0.24);
            font-size: 22px;
            font-weight: 800;
        }}
        .app-brand__title {{
            font-size: 27px;
            line-height: 1.05;
            font-weight: 800;
            background: linear-gradient(90deg, #ffffff 0%, #ffb800 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            white-space: nowrap;
        }}
        .app-brand__subtitle {{
            color: rgba(255,255,255,0.44);
            font-size: 11px;
            margin-top: 5px;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }}
        .partner-card {{
            background: rgba(255,255,255,0.025);
            border: 1px solid rgba(255,255,255,0.07);
            border-radius: 8px;
            padding: 10px 14px;
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 260px;
            justify-content: flex-start;
        }}
        .partner-card img {{
            width: 38px;
            height: 38px;
            object-fit: contain;
        }}
        .partner-card__name {{
            color: rgba(255,255,255,0.86);
            font-size: 12px;
            line-height: 1.25;
            font-weight: 750;
        }}
        .partner-card__link {{
            color: rgba(255,255,255,0.42);
            font-size: 10px;
            text-decoration: none;
        }}
        @media (max-width: 900px) {{
            .app-shell-header {{
                align-items: flex-start;
                flex-direction: column;
            }}
            .app-brand__title {{
                font-size: 24px;
                white-space: normal;
            }}
            .partner-card {{
                width: 100%;
                min-width: 0;
            }}
        }}
        </style>
        <div class="app-shell-header">
            <div class="app-brand">
                <div class="app-brand__mark">☼</div>
                <div>
                    <div class="app-brand__title">SkyGrid Solar AI</div>
                    <div class="app-brand__subtitle">Система моніторингу та прогнозування сонячної генерації</div>
                </div>
            </div>
            <div class="partner-card">
                <img src="{logo_url}" alt="НЗФ logo">
                <div>
                    <div class="partner-card__name">Нікопольський завод феросплавів</div>
                    <a class="partner-card__link" href="https://www.nzf.com.ua" target="_blank">nzf.com.ua</a>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _clean_numeric(df, columns):
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(',', '.', regex=False)
                .str.strip()
                .replace('', '0')
                .replace('nan', '0')
            )
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df


def _style_forecast_dashboard():
    st.markdown(
        """
        <style>
        .forecast-card {
            position: relative;
            overflow: hidden;
            background: linear-gradient(135deg, rgba(17,22,34,0.98) 0%, rgba(11,17,26,0.98) 100%);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 22px 22px 20px;
            min-height: 164px;
            box-shadow: 0 18px 36px rgba(0,0,0,0.30);
            transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        }
        .forecast-card:hover {
            border-color: var(--card-hover-border);
            transform: translateY(-2px);
            box-shadow: 0 22px 44px rgba(0,0,0,0.34);
        }
        .forecast-card__label {
            color: rgba(255,255,255,0.72);
            font-size: 13px;
            font-weight: 650;
            text-transform: uppercase;
            margin-bottom: 22px;
            padding-right: 48px;
        }
        .forecast-card__value {
            color: var(--card-accent);
            font-size: 34px;
            line-height: 1.1;
            font-weight: 750;
            white-space: nowrap;
        }
        .forecast-card__unit {
            font-size: 18px;
            color: var(--card-accent);
        }
        .forecast-card__icon {
            position: absolute;
            top: 20px;
            right: 20px;
            width: 42px;
            height: 42px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--card-accent);
            background: var(--card-icon-bg);
            box-shadow: 0 0 22px var(--card-glow);
            font-size: 21px;
        }
        .forecast-card__note {
            color: rgba(255,255,255,0.56);
            font-size: 12px;
            margin-top: 14px;
        }
        .forecast-card__badge {
            display: inline-block;
            margin-right: 8px;
            padding: 3px 8px;
            border-radius: 999px;
            color: var(--card-accent);
            background: var(--card-badge-bg);
            font-weight: 700;
        }
        .forecast-card__track {
            position: absolute;
            left: 22px;
            right: 22px;
            bottom: 18px;
            height: 5px;
            border-radius: 999px;
            background: rgba(255,255,255,0.08);
            overflow: hidden;
        }
        .forecast-card__track-fill {
            height: 100%;
            width: var(--card-progress);
            border-radius: inherit;
            background: var(--card-accent);
            box-shadow: 0 0 18px var(--card-glow);
        }
        .weather-day {
            background: linear-gradient(135deg, rgba(16,22,34,0.96), rgba(10,15,24,0.98));
            border: 1px solid rgba(255,255,255,0.09);
            border-radius: 8px;
            padding: 18px 20px;
            min-height: 190px;
            box-shadow: 0 16px 32px rgba(0,0,0,0.26);
            transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
        }
        .weather-day:hover {
            border-color: var(--weather-hover-border);
            transform: translateY(-2px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.32);
        }
        .weather-day__header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding-bottom: 12px;
            margin-bottom: 16px;
            border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .weather-day__date {
            color: rgba(255,255,255,0.70);
            font-size: 14px;
            font-weight: 650;
        }
        .weather-day__status {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background: var(--weather-status-bg);
            color: var(--weather-status-color);
            border: 1px solid var(--weather-status-border);
            font-size: 11px;
            font-weight: 750;
            text-transform: uppercase;
            white-space: nowrap;
        }
        .weather-day__icon {
            font-size: 34px;
            line-height: 1.25;
            filter: drop-shadow(0 0 12px rgba(255,184,0,0.28));
        }
        .weather-day__body {
            display: flex;
            align-items: stretch;
            justify-content: space-between;
            gap: 18px;
        }
        .weather-day__weather {
            flex: 1;
            min-width: 0;
        }
        .weather-day__meta {
            color: rgba(255,255,255,0.78);
            font-size: 12px;
            line-height: 1.75;
            margin-top: 10px;
        }
        .weather-day__temp {
            color: #ffffff;
            font-size: 27px;
            font-weight: 750;
            margin-left: 8px;
            vertical-align: middle;
        }
        .weather-day__solar {
            flex: 0 0 46%;
            border: 1px dashed var(--weather-solar-border);
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 102px;
            background: rgba(255,255,255,0.025);
            box-shadow: inset 0 0 18px rgba(255,255,255,0.018);
        }
        .weather-day__solar-label {
            color: rgba(255,255,255,0.48);
            font-size: 11px;
            font-weight: 750;
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        .weather-day__solar-value {
            color: var(--weather-accent);
            font-size: 26px;
            line-height: 1;
            font-weight: 800;
        }
        .weather-day__solar-unit {
            color: rgba(255,255,255,0.52);
            font-size: 12px;
            font-weight: 700;
            margin-top: 5px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _weather_icon(cloudcover, precipprob=0):
    cloudcover = float(cloudcover or 0)
    precipprob = float(precipprob or 0)
    if precipprob >= 45:
        return "🌧️"
    if cloudcover >= 70:
        return "☁️"
    if cloudcover >= 30:
        return "🌤️"
    return "☀️"


def _month_fact_mwh(df_h, now_ua):
    if df_h is None or df_h.empty or 'Time' not in df_h.columns or 'Fact_MW' not in df_h.columns:
        return 0.0, None

    df = _clean_numeric(df_h, ['Fact_MW'])
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time'])
    month_mask = (
        (df['Time'].dt.year == now_ua.year) &
        (df['Time'].dt.month == now_ua.month)
    )
    month_df = df[month_mask]
    if month_df.empty:
        return 0.0, None

    return float(month_df['Fact_MW'].sum()), month_df['Time'].max()


def _clamp_pct(value):
    return max(0.0, min(100.0, float(value or 0)))


def _day_label(day, now_ua):
    day_ts = pd.to_datetime(day)
    today = pd.Timestamp(now_ua.date())
    if day_ts.date() == today.date():
        prefix = "Сьогодні"
    elif day_ts.date() == (today + pd.Timedelta(days=1)).date():
        prefix = "Завтра"
    else:
        weekdays = {
            0: "Понеділок",
            1: "Вівторок",
            2: "Середа",
            3: "Четвер",
            4: "П'ятниця",
            5: "Субота",
            6: "Неділя",
        }
        prefix = weekdays.get(day_ts.weekday(), "")
    return f"{prefix}, {day_ts.strftime('%d.%m')}"


def _tomorrow_start(now_ua):
    return pd.Timestamp((now_ua + pd.Timedelta(days=1)).date())


def draw_metrics(df_f, df_h, now_ua, timedelta):
    _style_forecast_dashboard()
    df = _clean_numeric(df_f, ['AI_MW', 'Forecast_MW', 'Capacity_MW'])
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time']).sort_values('Time')

    tomorrow = (now_ua + timedelta(days=1)).date()
    tomorrow_df = df[df['Time'].dt.date == tomorrow]

    tomorrow_mwh = float(tomorrow_df['AI_MW'].sum()) if not tomorrow_df.empty else 0.0
    peak_mw = float(tomorrow_df['AI_MW'].max()) if not tomorrow_df.empty else 0.0
    peak_time = "12:00-13:00"
    if not tomorrow_df.empty and peak_mw > 0:
        peak_row = tomorrow_df.loc[tomorrow_df['AI_MW'].idxmax()]
        peak_time = pd.to_datetime(peak_row['Time']).strftime('%H:%M')

    capacity_mw = float(df['Capacity_MW'].max()) if 'Capacity_MW' in df.columns and not df.empty else 0.0
    full_load_hours = (tomorrow_mwh / capacity_mw) if capacity_mw > 0 else 0.0
    month_fact_mwh, month_last_time = _month_fact_mwh(df_h, now_ua)
    month_note = "фактична генерація за поточний місяць"
    if month_last_time is not None:
        month_note = f"останній факт: {pd.to_datetime(month_last_time).strftime('%d.%m %H:%M')}"
    peak_pct = (peak_mw / capacity_mw * 100) if capacity_mw > 0 else 0.0
    month_capacity_factor = 0.0
    if capacity_mw > 0 and now_ua.day > 0:
        month_capacity_factor = month_fact_mwh / (capacity_mw * 24 * now_ua.day) * 100
    month_freshness = 100.0 if month_last_time is not None and pd.to_datetime(month_last_time).date() >= now_ua.date() else 72.0

    cards = [
        {
            "label": "Прогноз на завтра",
            "value": f"{tomorrow_mwh:.1f}",
            "unit": "МВт·год",
            "badge": f"{full_load_hours:.1f} год",
            "note": "еквівалент роботи на повній потужності",
            "icon": "↗",
            "accent": "#ffb800",
            "glow": "rgba(255,184,0,0.22)",
            "progress": _clamp_pct(full_load_hours / 12 * 100),
        },
        {
            "label": "Пік генерації завтра",
            "value": f"{peak_mw:.1f}",
            "unit": "МВт",
            "badge": peak_time,
            "note": "очікуваний пік інсоляції",
            "icon": "⚡",
            "accent": "#00f0ff",
            "glow": "rgba(0,240,255,0.20)",
            "progress": _clamp_pct(peak_pct),
        },
        {
            "label": "Факт з початку місяця",
            "value": f"{month_fact_mwh:.1f}",
            "unit": "МВт·год",
            "badge": f"КВВП {month_capacity_factor:.1f}%" if month_capacity_factor > 0 else "Оновлено",
            "note": month_note,
            "icon": "▣",
            "accent": "#10b981",
            "glow": "rgba(16,185,129,0.18)",
            "progress": _clamp_pct(month_freshness),
        },
    ]

    for col, card in zip(st.columns(3), cards):
        style = (
            f"--card-accent:{card['accent']};"
            f"--card-glow:{card['glow']};"
            f"--card-border:{card['accent']}33;"
            f"--card-hover-border:{card['accent']}66;"
            f"--card-icon-bg:{card['accent']}18;"
            f"--card-badge-bg:{card['accent']}1f;"
            f"--card-progress:{card['progress']:.0f}%;"
        )
        with col:
            st.markdown(
                f"""
                <div class="forecast-card" style="{style}">
                    <div class="forecast-card__label">{card['label']}</div>
                    <div class="forecast-card__icon">{card['icon']}</div>
                    <div class="forecast-card__value">
                        {card['value']} <span class="forecast-card__unit">{card['unit']}</span>
                    </div>
                    <div class="forecast-card__note">
                        <span class="forecast-card__badge">{card['badge']}</span>{card['note']}
                    </div>
                    <div class="forecast-card__track">
                        <div class="forecast-card__track-fill"></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def draw_weather_strip(df_f, now_ua, timedelta):
    _style_forecast_dashboard()
    df = _clean_numeric(df_f, ['CloudCover', 'Temp', 'PrecipProb', 'AI_MW', 'Forecast_MW', 'WindSpeed'])
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time']).sort_values('Time')
    forecast_start = _tomorrow_start(now_ua)
    forecast_end = forecast_start + pd.Timedelta(days=3)
    df = df[(df['Time'] >= forecast_start) & (df['Time'] < forecast_end)]

    st.markdown("##### Погода, що впливає на прогноз")
    if df.empty:
        st.info("Немає погодних даних для найближчих 3 днів.")
        return

    agg_map = {}
    if 'Temp' in df.columns:
        agg_map['Temp'] = ['min', 'max', 'mean']
    if 'CloudCover' in df.columns:
        agg_map['CloudCover'] = ['mean', 'max']
    if 'PrecipProb' in df.columns:
        agg_map['PrecipProb'] = 'max'
    if 'AI_MW' in df.columns:
        agg_map['AI_MW'] = 'sum'
    if 'WindSpeed' in df.columns:
        agg_map['WindSpeed'] = 'mean'
    if not agg_map:
        st.info("Немає погодних колонок для добових плиток.")
        return
    daily = df.groupby(df['Time'].dt.date).agg(agg_map)
    daily.columns = ['_'.join(col).strip('_') for col in daily.columns.to_flat_index()]
    daily = daily.reset_index().head(3)

    for col, row in zip(st.columns(3), daily.to_dict('records')):
        date_label = _day_label(row['Time'], now_ua)
        temp_min = float(row.get('Temp_min', 0))
        temp_max = float(row.get('Temp_max', 0))
        cloud_avg = float(row.get('CloudCover_mean', 0))
        cloud_max = float(row.get('CloudCover_max', 0))
        precip_max = float(row.get('PrecipProb_max', 0))
        day_mwh = float(row.get('AI_MW_sum', 0))
        wind_avg = float(row.get('WindSpeed_mean', 0))
        icon = _weather_icon(cloud_avg, precip_max)
        risk = "сприятливо"
        accent = "#10b981"
        status_bg = "rgba(16,185,129,0.14)"
        status_border = "rgba(16,185,129,0.30)"
        if precip_max >= 45:
            risk = "ризик опадів"
            accent = "#ffb800"
            status_bg = "rgba(255,184,0,0.14)"
            status_border = "rgba(255,184,0,0.34)"
        elif cloud_max >= 75:
            risk = "пікова хмарність"
            accent = "#ffb800"
            status_bg = "rgba(255,184,0,0.14)"
            status_border = "rgba(255,184,0,0.34)"
        elif cloud_avg >= 55:
            risk = "нестабільна генерація"
            accent = "#00f0ff"
            status_bg = "rgba(0,240,255,0.12)"
            status_border = "rgba(0,240,255,0.28)"
        weather_style = (
            f"--weather-accent:{accent};"
            f"--weather-status-color:{accent};"
            f"--weather-status-bg:{status_bg};"
            f"--weather-status-border:{status_border};"
            f"--weather-solar-border:{accent}55;"
            f"--weather-hover-border:{accent}66;"
        )
        with col:
            st.markdown(
                f"""
                <div class="weather-day" style="{weather_style}">
                    <div class="weather-day__header">
                        <div class="weather-day__date">{date_label}</div>
                        <div class="weather-day__status">{risk}</div>
                    </div>
                    <div class="weather-day__body">
                        <div class="weather-day__weather">
                            <div>
                                <span class="weather-day__icon">{icon}</span>
                                <span class="weather-day__temp">{temp_max:.0f}°C</span>
                            </div>
                            <div class="weather-day__meta">
                                ☁ Хмарність: {cloud_avg:.0f}% / пік {cloud_max:.0f}%<br>
                                ☔ Опади: до {precip_max:.0f}%<br>
                                ≋ Вітер: {wind_avg:.1f} м/с<br>
                                Мін. температура: {temp_min:.0f}°C
                            </div>
                        </div>
                        <div class="weather-day__solar">
                            <div class="weather-day__solar-label">Прогноз СЕС</div>
                            <div class="weather-day__solar-value">{day_mwh:.1f}</div>
                            <div class="weather-day__solar-unit">МВт·год</div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def draw_main_chart(df_f, now_ua=None):
    df = _clean_numeric(df_f, ['Forecast_MW', 'AI_MW'])
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time']).sort_values('Time')

    if now_ua is not None:
        forecast_start = _tomorrow_start(now_ua)
        forecast_end = forecast_start + pd.Timedelta(days=3)
        df_plot = df[(df['Time'] >= forecast_start) & (df['Time'] < forecast_end)]
    else:
        cutoff = df['Time'].min() + pd.Timedelta(days=3)
        df_plot = df[df['Time'] < cutoff]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot['Time'], y=df_plot['Forecast_MW'],
        name='Прогноз сайту', mode='lines',
        line=dict(color='#F47B45', width=1.8, dash='dot'),
        hovertemplate='%{y:.2f} МВт<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=df_plot['Time'], y=df_plot['AI_MW'],
        name='Прогноз ШІ', mode='lines',
        line=dict(color='#37D7FF', width=3),
        fill='tozeroy', fillcolor='rgba(55,215,255,0.18)',
        hovertemplate='%{y:.2f} МВт<extra></extra>',
    ))

    if now_ua is not None and not df_plot.empty:
        today_end = pd.Timestamp(now_ua.date()) + pd.Timedelta(days=1)
        if df_plot['Time'].min() < today_end <= df_plot['Time'].max():
            fig.add_vline(
                x=today_end,
                line_width=1,
                line_dash='dash',
                line_color='rgba(255,255,255,0.45)',
                annotation_text='Сьогодні / прогноз',
                annotation_position='top',
            )

    fig.update_layout(
        height=430, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='МВт', gridcolor='rgba(255,255,255,0.10)'),
        xaxis=dict(title='Час', gridcolor='rgba(255,255,255,0.06)'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        hovermode='x unified',
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
    )
    st.plotly_chart(fig, width='stretch')
