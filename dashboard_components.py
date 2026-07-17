import pandas as pd
import plotly.graph_objects as go
import streamlit as st


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
            background: rgba(255,255,255,0.055);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 8px;
            padding: 18px 18px 16px;
            min-height: 138px;
        }
        .forecast-card__label {
            color: rgba(255,255,255,0.72);
            font-size: 13px;
            font-weight: 650;
            margin-bottom: 10px;
        }
        .forecast-card__value {
            color: #ffffff;
            font-size: 34px;
            line-height: 1.1;
            font-weight: 750;
            white-space: nowrap;
        }
        .forecast-card__note {
            color: rgba(255,255,255,0.56);
            font-size: 12px;
            margin-top: 12px;
        }
        .weather-day {
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px;
            padding: 12px 14px;
            min-height: 112px;
        }
        .weather-day__date {
            color: rgba(255,255,255,0.70);
            font-size: 12px;
            font-weight: 650;
        }
        .weather-day__icon {
            font-size: 30px;
            line-height: 1.25;
            margin: 4px 0;
        }
        .weather-day__top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 8px;
        }
        .weather-day__forecast {
            color: #ffffff;
            font-size: 20px;
            font-weight: 750;
            white-space: nowrap;
        }
        .weather-day__meta {
            color: rgba(255,255,255,0.78);
            font-size: 12px;
            line-height: 1.55;
        }
        .weather-day__risk {
            display: inline-block;
            margin-top: 10px;
            padding: 3px 8px;
            border-radius: 999px;
            background: rgba(55,215,255,0.12);
            color: #8fe9ff;
            font-size: 11px;
            font-weight: 650;
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
    capacity_pct = (tomorrow_mwh / (capacity_mw * 24) * 100) if capacity_mw > 0 else 0.0
    month_fact_mwh, month_last_time = _month_fact_mwh(df_h, now_ua)
    month_note = "фактична генерація за поточний місяць"
    if month_last_time is not None:
        month_note = f"останній факт: {pd.to_datetime(month_last_time).strftime('%d.%m %H:%M')}"

    cards = [
        ("Прогноз на завтра", f"{tomorrow_mwh:.1f} МВт·год", f"{capacity_pct:.1f}% від номінальної потужності СЕС"),
        ("Пік генерації завтра", f"{peak_mw:.1f} МВт", f"очікуваний максимум о {peak_time}"),
        ("Факт з початку місяця", f"{month_fact_mwh:.1f} МВт·год", month_note),
    ]

    for col, (label, value, note) in zip(st.columns(3), cards):
        with col:
            st.markdown(
                f"""
                <div class="forecast-card">
                    <div class="forecast-card__label">{label}</div>
                    <div class="forecast-card__value">{value}</div>
                    <div class="forecast-card__note">{note}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def draw_weather_strip(df_f, now_ua, timedelta):
    _style_forecast_dashboard()
    df = _clean_numeric(df_f, ['CloudCover', 'Temp', 'PrecipProb', 'AI_MW', 'Forecast_MW', 'WindSpeed'])
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time']).sort_values('Time')
    df = df[(df['Time'] >= now_ua) & (df['Time'] < now_ua + timedelta(days=3))]

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
        date_label = pd.to_datetime(row['Time']).strftime('%d.%m')
        temp_min = float(row.get('Temp_min', 0))
        temp_max = float(row.get('Temp_max', 0))
        cloud_avg = float(row.get('CloudCover_mean', 0))
        cloud_max = float(row.get('CloudCover_max', 0))
        precip_max = float(row.get('PrecipProb_max', 0))
        day_mwh = float(row.get('AI_MW_sum', 0))
        wind_avg = float(row.get('WindSpeed_mean', 0))
        icon = _weather_icon(cloud_avg, precip_max)
        risk = "сприятливо"
        if precip_max >= 45:
            risk = "ризик опадів"
        elif cloud_max >= 75:
            risk = "пікова хмарність"
        elif cloud_avg >= 55:
            risk = "нестабільна генерація"
        with col:
            st.markdown(
                f"""
                <div class="weather-day">
                    <div class="weather-day__top">
                        <div>
                            <div class="weather-day__date">{date_label}</div>
                            <div class="weather-day__icon">{icon}</div>
                        </div>
                        <div class="weather-day__forecast">{day_mwh:.1f} МВт·год</div>
                    </div>
                    <div class="weather-day__meta">
                        Температура: {temp_min:.0f}–{temp_max:.0f} °C<br>
                        Хмарність: {cloud_avg:.0f}% середня / {cloud_max:.0f}% пік<br>
                        Опади: до {precip_max:.0f}%<br>
                        Вітер: {wind_avg:.1f} м/с
                    </div>
                    <div class="weather-day__risk">{risk}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def draw_main_chart(df_f, now_ua=None):
    df = _clean_numeric(df_f, ['Forecast_MW', 'AI_MW'])
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time']).sort_values('Time')

    if now_ua is not None:
        df_plot = df[(df['Time'] >= now_ua) & (df['Time'] < now_ua + pd.Timedelta(hours=72))]
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
        if df_plot['Time'].min() <= today_end <= df_plot['Time'].max():
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
