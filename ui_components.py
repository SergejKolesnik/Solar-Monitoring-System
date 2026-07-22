import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


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


# ─────────────────────────────────────────────
#  ВКЛАДКА 0: МОНІТОРИНГ
# ─────────────────────────────────────────────

def draw_metrics(df_f, now_ua, timedelta):
    current = df_f[df_f['Time'] >= now_ua].head(1)
    next3   = df_f[df_f['Time'] >= now_ua].head(3)

    ai_now    = float(current['AI_MW'].values[0])       if not current.empty else 0.0
    fc_now    = float(current['Forecast_MW'].values[0]) if not current.empty else 0.0
    ai_3h     = float(next3['AI_MW'].mean())             if not next3.empty  else 0.0
    daily_sum = float(df_f[df_f['Time'].dt.date == now_ua.date()]['AI_MW'].sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⚡ Зараз (ШІ)",    f"{ai_now:.2f} МВт",  f"Сайт: {fc_now:.2f}")
    c2.metric("📈 Середнє 3 год", f"{ai_3h:.2f} МВт")
    c3.metric("☀️ День (план)",   f"{daily_sum:.1f} МВт·год")
    c4.metric("🕐 Час (Київ)",    now_ua.strftime("%H:%M"))


def draw_main_chart(df_f):
    cutoff = df_f['Time'].min() + pd.Timedelta(days=5)
    df_plot = df_f[df_f['Time'] <= cutoff]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot['Time'], y=df_plot['Forecast_MW'],
        name='Прогноз сайту', mode='lines',
        line=dict(color='#D85A30', width=1.5, dash='dot')
    ))
    fig.add_trace(go.Scatter(
        x=df_plot['Time'], y=df_plot['AI_MW'],
        name='План ШІ', mode='lines',
        line=dict(color='#378ADD', width=2),
        fill='tozeroy', fillcolor='rgba(55,138,221,0.07)'
    ))
    fig.update_layout(
        height=360, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='МВт'), xaxis=dict(title='Час'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        hovermode='x unified'
    )
    st.plotly_chart(fig, width='stretch')


def _latest_positive_time(df, value_col):
    if value_col not in df.columns or 'Time' not in df.columns:
        return None
    values = pd.to_numeric(df[value_col], errors='coerce').fillna(0)
    times = pd.to_datetime(df['Time'], errors='coerce')
    valid = df[(values > 0.05) & times.notna()].copy()
    if valid.empty:
        return None
    return pd.to_datetime(valid['Time']).max()


def _format_time(value):
    if value is None or pd.isna(value):
        return "немає даних"
    return pd.to_datetime(value).strftime('%d.%m.%Y %H:%M')


def _age_badge(value, now_kyiv, stale_hours):
    if value is None or pd.isna(value):
        return "немає"
    hours = max((now_kyiv - pd.to_datetime(value)).total_seconds() / 3600, 0)
    label = f"{hours:.0f} год. тому"
    return label if hours <= stale_hours else f"{label} / перевірити"


def _day_energy(df, day, value_col):
    if value_col not in df.columns or 'Time' not in df.columns:
        return 0.0
    start = pd.Timestamp(day)
    end = start + pd.Timedelta(days=1)
    mask = (df['Time'] >= start) & (df['Time'] < end)
    return float(pd.to_numeric(df.loc[mask, value_col], errors='coerce').fillna(0).sum())


def _draw_ai_data_diagnostics(df):
    now_kyiv = pd.Timestamp.now(tz='Europe/Kyiv').tz_localize(None)
    tomorrow = (now_kyiv.normalize() + pd.Timedelta(days=1)).date()

    last_fact_time = _latest_positive_time(df, 'Fact_MW')
    last_base_time = _latest_positive_time(df, 'Forecast_MW')
    last_ai_time = _latest_positive_time(df, 'AI_Forecast_MW')

    st.markdown("##### Діагностика даних для прогнозу")
    c1, c2, c3 = st.columns(3)
    c1.metric("Останній факт АСКОЕ", _format_time(last_fact_time), _age_badge(last_fact_time, now_kyiv, 36))
    c2.metric("Останній базовий прогноз", _format_time(last_base_time), _age_badge(last_base_time, now_kyiv, 72))
    c3.metric("Останній прогноз ШІ", _format_time(last_ai_time), _age_badge(last_ai_time, now_kyiv, 72))

    expected_lag_days = 2 if now_kyiv.hour < 9 else 1
    expected_latest_date = (now_kyiv.normalize() - pd.Timedelta(days=expected_lag_days)).date()
    issues = []
    if last_fact_time is None:
        issues.append("У базі немає фактичної генерації АСКОЕ.")
    elif last_fact_time.date() < expected_latest_date:
        issues.append(
            f"Факт АСКОЕ відстає: останній запис {last_fact_time.strftime('%d.%m.%Y %H:%M')}, "
            f"очікувався звіт за {expected_latest_date.strftime('%d.%m.%Y')}."
        )

    base_tomorrow = _day_energy(df, tomorrow, 'Forecast_MW')
    ai_tomorrow = _day_energy(df, tomorrow, 'AI_Forecast_MW')

    fact_rows = pd.DataFrame()
    recent_fact_median = 0.0
    if 'Fact_MW' in df.columns:
        fact_values = pd.to_numeric(df['Fact_MW'], errors='coerce').fillna(0)
        fact_rows = df[fact_values > 0.05].copy()
    if not fact_rows.empty:
        fact_rows['Дата'] = fact_rows['Time'].dt.date
        fact_daily = fact_rows.groupby('Дата')['Fact_MW'].sum().reset_index()
        recent_fact_median = float(pd.to_numeric(fact_daily.tail(14)['Fact_MW'], errors='coerce').median())

    if ai_tomorrow <= 0 and base_tomorrow > 0:
        issues.append("На завтра є базовий прогноз, але немає збереженого прогнозу ШІ.")
    elif ai_tomorrow > 0 and base_tomorrow > 0:
        diff_pct = abs(ai_tomorrow - base_tomorrow) / max(base_tomorrow, ai_tomorrow) * 100
        if diff_pct >= 45:
            issues.append(
                f"Прогноз ШІ на завтра суттєво відрізняється від базового прогнозу: "
                f"ШІ {ai_tomorrow:.1f} МВт·год vs база {base_tomorrow:.1f} МВт·год."
            )

    if ai_tomorrow > 0 and recent_fact_median > 0 and ai_tomorrow < recent_fact_median * 0.35:
        issues.append(
            f"Прогноз ШІ на завтра нетипово низький: {ai_tomorrow:.1f} МВт·год "
            f"проти медіани останніх днів {recent_fact_median:.1f} МВт·год."
        )

    c4, c5, c6 = st.columns(3)
    c4.metric("ШІ на завтра", f"{ai_tomorrow:.1f} МВт·год")
    c5.metric("Базовий прогноз на завтра", f"{base_tomorrow:.1f} МВт·год")
    c6.metric("Медіана факту 14 днів", f"{recent_fact_median:.1f} МВт·год")

    if issues:
        st.warning(" ".join(issues))
    else:
        st.success("Дані для контролю прогнозу виглядають узгоджено: критичних затримок або нетипових відхилень не видно.")

    st.write("---")


def _infer_error_factor(row):
    factors = []
    cloud_avg = float(row.get('Хмарність середня %', 0) or 0)
    cloud_peak = float(row.get('Хмарність пік %', 0) or 0)
    precip = float(row.get('Опади макс. %', 0) or 0)
    wind = float(row.get('Вітер середній м/с', 0) or 0)
    ai_mape = float(row.get('MAPE ШІ %', 0) or 0)
    base_mape = float(row.get('MAPE бази %', 0) or 0)
    fact = float(row.get('Факт МВт·год', 0) or 0)
    ai = float(row.get('ШІ МВт·год', 0) or 0)

    if cloud_peak >= 75 or cloud_avg >= 55:
        factors.append("ймовірна причина: хмарність")
    if precip >= 40:
        factors.append("ймовірна причина: опади")
    if wind >= 14:
        factors.append("можливий фактор: сильний вітер")
    if ai_mape > base_mape + 15:
        factors.append("ШІ гірший за базовий прогноз")
    if fact > 0 and ai > fact * 1.6 and cloud_avg < 35:
        factors.append("можливе переоцінювання інсоляції")
    if fact > 0 and ai < fact * 0.45 and cloud_avg < 45 and precip < 25:
        factors.append("можливе обмеження/нетипова робота СЕС")

    if not factors:
        factors.append("потрібен ручний розбір")
    return "; ".join(factors[:3])


def _build_error_factor_table(df_fact):
    agg = {
        'Факт МВт·год': ('Fact_MW', 'sum'),
        'База МВт·год': ('Forecast_MW', 'sum'),
        'ШІ МВт·год': ('AI_Forecast_MW', 'sum'),
        'MAPE бази %': ('Base_Abs_Error_Pct', 'mean'),
        'MAPE ШІ %': ('AI_Abs_Error_Pct', 'mean'),
    }
    if 'CloudCover' in df_fact.columns:
        agg['Хмарність середня %'] = ('CloudCover', 'mean')
        agg['Хмарність пік %'] = ('CloudCover', 'max')
    if 'PrecipProb' in df_fact.columns:
        agg['Опади макс. %'] = ('PrecipProb', 'max')
    if 'WindSpeed' in df_fact.columns:
        agg['Вітер середній м/с'] = ('WindSpeed', 'mean')
    if 'Temp' in df_fact.columns:
        agg['Температура середня °C'] = ('Temp', 'mean')

    factors = df_fact.groupby('Дата').agg(**agg).reset_index()
    factors['Абс. помилка ШІ МВт·год'] = (factors['ШІ МВт·год'] - factors['Факт МВт·год']).abs()
    factors['ШІ гірший за базу'] = factors['MAPE ШІ %'] > factors['MAPE бази %']

    defaults = {
        'Хмарність середня %': 0.0,
        'Хмарність пік %': 0.0,
        'Опади макс. %': 0.0,
        'Вітер середній м/с': 0.0,
        'Температура середня °C': 0.0,
    }
    for col, default in defaults.items():
        if col not in factors.columns:
            factors[col] = default

    factors['Ймовірна причина'] = factors.apply(_infer_error_factor, axis=1)
    numeric_cols = [
        'Факт МВт·год', 'База МВт·год', 'ШІ МВт·год',
        'MAPE бази %', 'MAPE ШІ %', 'Абс. помилка ШІ МВт·год',
        'Хмарність середня %', 'Хмарність пік %', 'Опади макс. %',
        'Вітер середній м/с', 'Температура середня °C'
    ]
    for col in numeric_cols:
        factors[col] = pd.to_numeric(factors[col], errors='coerce').fillna(0).round(1)
    return factors.sort_values('MAPE ШІ %', ascending=False)


def _cloud_bucket(cloud_value):
    cloud = float(cloud_value or 0)
    if cloud < 25:
        return "0-25%"
    if cloud < 50:
        return "25-50%"
    if cloud < 75:
        return "50-75%"
    return "75-100%"


def _build_shadow_experiment(df_fact, lookback_days=30, min_samples=6):
    """
    Builds a past-only shadow forecast from historical rows.

    The production AI forecast is not changed. For every historical day we look only
    at previous days with similar cloudiness and estimate a conservative correction
    factor from Fact_MW / AI_Forecast_MW.
    """
    required = {'Time', 'Fact_MW', 'Forecast_MW', 'AI_Forecast_MW'}
    if df_fact.empty or not required.issubset(df_fact.columns):
        return pd.DataFrame()

    df = df_fact.copy()
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time']).sort_values('Time')
    df['Date'] = df['Time'].dt.date
    cloud_source = df['CloudCover'] if 'CloudCover' in df.columns else pd.Series([0] * len(df), index=df.index)
    df['Cloud_Bucket'] = cloud_source.apply(_cloud_bucket)
    df['AI_Experimental_MW'] = pd.NA
    df['Shadow_Factor'] = pd.NA
    df['Shadow_Samples'] = 0

    valid_ratio_mask = (
        (df['Fact_MW'] > 0.05) &
        (df['AI_Forecast_MW'] > 0.05)
    )
    df_dates = pd.to_datetime(df['Date'])

    for day in sorted(df['Date'].dropna().unique()):
        day_ts = pd.Timestamp(day)
        history_start = day_ts - pd.Timedelta(days=lookback_days)
        history = df[
            valid_ratio_mask &
            (df_dates < day_ts) &
            (df_dates >= history_start)
        ].copy()
        if history.empty:
            continue

        day_rows = df[df['Date'] == day].copy()
        for bucket in day_rows['Cloud_Bucket'].dropna().unique():
            bucket_history = history[history['Cloud_Bucket'] == bucket].copy()
            correction_source = bucket_history if len(bucket_history) >= min_samples else history
            if len(correction_source) < min_samples:
                continue

            ratios = (
                correction_source['Fact_MW'] / correction_source['AI_Forecast_MW'].replace(0, pd.NA)
            ).replace([pd.NA, float('inf'), -float('inf')], pd.NA).dropna()
            if ratios.empty:
                continue

            # Conservative clipping avoids one abnormal day turning into a wild forecast.
            factor = float(ratios.median())
            factor = max(0.70, min(1.30, factor))

            idx = df[(df['Date'] == day) & (df['Cloud_Bucket'] == bucket)].index
            corrected = pd.to_numeric(df.loc[idx, 'AI_Forecast_MW'], errors='coerce').fillna(0) * factor
            if 'Capacity_MW' in df.columns:
                cap = pd.to_numeric(df.loc[idx, 'Capacity_MW'], errors='coerce').fillna(0)
                corrected = corrected.clip(lower=0, upper=cap.where(cap > 0, corrected).mul(1.05))
            else:
                corrected = corrected.clip(lower=0)

            df.loc[idx, 'AI_Experimental_MW'] = corrected
            df.loc[idx, 'Shadow_Factor'] = factor
            df.loc[idx, 'Shadow_Samples'] = len(correction_source)

    shadow = df[df['AI_Experimental_MW'].notna()].copy()
    if shadow.empty:
        return shadow

    shadow['AI_Experimental_MW'] = pd.to_numeric(shadow['AI_Experimental_MW'], errors='coerce').fillna(0)
    shadow = shadow[shadow['AI_Experimental_MW'] > 0.05].copy()
    if shadow.empty:
        return shadow

    shadow['Experimental_Error_Pct'] = (
        (shadow['Fact_MW'] - shadow['AI_Experimental_MW']) /
        shadow['Fact_MW'].replace(0, pd.NA) * 100
    )
    shadow['Experimental_Abs_Error_Pct'] = pd.to_numeric(
        shadow['Experimental_Error_Pct'], errors='coerce'
    ).abs().fillna(0)
    return shadow


def _draw_shadow_experiment(df_fact):
    shadow = _build_shadow_experiment(df_fact)
    if shadow.empty:
        st.markdown("##### Shadow-mode: експериментальна корекція ШІ")
        st.info(
            "Поки недостатньо історії для чесного shadow-тесту. Потрібні попередні дні з фактом, "
            "AI_Forecast_MW і погодними параметрами."
        )
        st.write("---")
        return

    st.markdown("##### Shadow-mode: експериментальна корекція ШІ")
    st.caption(
        "Це безпечний паралельний тест. Робочий прогноз не змінюється: ми лише перевіряємо, "
        "чи корекція ШІ за попередніми помилками в схожій хмарності дає кращий результат."
    )

    daily = shadow.groupby('Date').agg(
        **{
            'Факт МВт·год': ('Fact_MW', 'sum'),
            'База МВт·год': ('Forecast_MW', 'sum'),
            'ШІ поточний МВт·год': ('AI_Forecast_MW', 'sum'),
            'ШІ експеримент МВт·год': ('AI_Experimental_MW', 'sum'),
            'MAPE бази %': ('Base_Abs_Error_Pct', 'mean'),
            'MAPE ШІ поточний %': ('AI_Abs_Error_Pct', 'mean'),
            'MAPE ШІ експеримент %': ('Experimental_Abs_Error_Pct', 'mean'),
            'Корекція середня': ('Shadow_Factor', 'mean'),
            'Семплів середньо': ('Shadow_Samples', 'mean'),
        }
    ).reset_index().sort_values('Date')

    daily['Покращення експерименту до ШІ %'] = (
        100 * (
            daily['MAPE ШІ поточний %'] - daily['MAPE ШІ експеримент %']
        ) / daily['MAPE ШІ поточний %'].replace(0, pd.NA)
    ).fillna(0)

    for col in daily.columns:
        if col != 'Date':
            daily[col] = pd.to_numeric(daily[col], errors='coerce').round(2)

    recent = daily.tail(30).copy()
    current_mape = float(recent['MAPE ШІ поточний %'].mean())
    exp_mape = float(recent['MAPE ШІ експеримент %'].mean())
    base_mape = float(recent['MAPE бази %'].mean())
    exp_improvement = 100 * (current_mape - exp_mape) / current_mape if current_mape > 0 else 0
    better_days = float((recent['MAPE ШІ експеримент %'] < recent['MAPE ШІ поточний %']).mean() * 100)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("MAPE поточного ШІ", f"{current_mape:.1f}%")
    c2.metric("MAPE експерименту", f"{exp_mape:.1f}%", f"{exp_improvement:+.1f}% до ШІ")
    c3.metric("Днів, де експеримент кращий", f"{better_days:.0f}%")
    c4.metric("MAPE бази", f"{base_mape:.1f}%")

    if exp_improvement >= 5 and better_days >= 60:
        st.success(
            "Експеримент виглядає перспективно: корекція покращує ШІ на більшості днів. "
            "Наступний крок - винести її у прогноз на майбутні дні також у shadow-mode."
        )
    elif exp_improvement <= -5:
        st.warning(
            "Експеримент поки погіршує результат. Це теж корисний висновок: таку корекцію "
            "не можна переводити в робочий прогноз без доопрацювання."
        )
    else:
        st.info(
            "Ефект експерименту поки нейтральний. Потрібно накопичити більше днів або уточнити "
            "ознаки: окремо ранкові/полуденні години, опади, пікова хмарність."
        )

    st.markdown("###### Добове порівняння за останні 30 днів")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=recent['Date'], y=recent['MAPE ШІ поточний %'],
        name='Поточний ШІ', mode='lines+markers',
        line=dict(color='#1D9E75', width=2, dash='dash')
    ))
    fig.add_trace(go.Scatter(
        x=recent['Date'], y=recent['MAPE ШІ експеримент %'],
        name='ШІ експеримент', mode='lines+markers',
        line=dict(color='#ffb800', width=2.5)
    ))
    fig.add_trace(go.Scatter(
        x=recent['Date'], y=recent['MAPE бази %'],
        name='База', mode='lines+markers',
        line=dict(color='#D85A30', width=1.8, dash='dot')
    ))
    fig.update_layout(
        height=280, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='MAPE, %'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        hovermode='x unified'
    )
    st.plotly_chart(fig, width='stretch')

    display_cols = [
        'Date', 'Факт МВт·год', 'ШІ поточний МВт·год', 'ШІ експеримент МВт·год',
        'MAPE ШІ поточний %', 'MAPE ШІ експеримент %',
        'Покращення експерименту до ШІ %', 'Корекція середня', 'Семплів середньо'
    ]
    st.dataframe(
        recent.sort_values('Date', ascending=False)[display_cols].style.background_gradient(
            subset=['Покращення експерименту до ШІ %'], cmap='RdYlGn', vmin=-20, vmax=20
        ),
        use_container_width=True,
        hide_index=True
    )
    st.write("---")


def _draw_error_factor_analysis(df_fact):
    factor_table = _build_error_factor_table(df_fact)
    if factor_table.empty:
        return

    top = factor_table.head(10).copy()
    st.markdown("##### Аналіз факторів похибки ШІ")
    st.caption(
        "Тут зібрані дні з найбільшою добовою помилкою ШІ. Це не змінює модель, "
        "а допомагає зрозуміти, на яких умовах вона помиляється."
    )

    high_cloud_days = int((factor_table['Хмарність пік %'] >= 75).sum())
    ai_worse_days = int(factor_table['ШІ гірший за базу'].sum())
    median_ai_mape = float(factor_table['MAPE ШІ %'].median()) if not factor_table.empty else 0.0
    c1, c2, c3 = st.columns(3)
    c1.metric("Днів із піковою хмарністю", high_cloud_days)
    c2.metric("Днів, де ШІ гірший за базу", ai_worse_days)
    c3.metric("Медіанна MAPE ШІ", f"{median_ai_mape:.1f}%")

    display_cols = [
        'Дата', 'Факт МВт·год', 'ШІ МВт·год', 'База МВт·год',
        'MAPE ШІ %', 'MAPE бази %', 'Хмарність середня %',
        'Хмарність пік %', 'Опади макс. %', 'Вітер середній м/с',
        'Ймовірна причина'
    ]
    st.dataframe(
        top[display_cols].style.background_gradient(
            subset=['MAPE ШІ %'], cmap='Reds', vmin=0, vmax=max(100, float(top['MAPE ШІ %'].max()))
        ),
        use_container_width=True,
        hide_index=True
    )

    st.write("---")


# ─────────────────────────────────────────────
#  ВКЛАДКА 1: НАВЧАННЯ
# ─────────────────────────────────────────────

def draw_training_tab(df_h):
    """
    Вкладка "Якість ШІ" НЕ навчає модель у Streamlit.
    Вона показує прогрес і аналізує вже збережені результати з Google Sheet:
      - Forecast_MW        = базовий прогноз сайту/погоди
      - AI_Forecast_MW     = прогноз, який записав collector.py
      - Fact_MW            = факт АСКОЕ
      - Forecast_Error_MW  = Fact_MW - Forecast_MW
      - AI_Error_MW        = Fact_MW - AI_Forecast_MW
    """

    if df_h.empty:
        st.info("База даних порожня.")
        return

    required = ['Time', 'Fact_MW', 'Forecast_MW', 'AI_Forecast_MW']
    missing = [c for c in required if c not in df_h.columns]
    if missing:
        st.warning(f"Для аналізу якості ШІ бракує колонок: {', '.join(missing)}")
        st.info("Спочатку запусти оновлений collector.py, щоб він створив AI_Forecast_MW та колонки помилок.")
        return

    num_cols = [
        'Fact_MW', 'Forecast_MW', 'AI_Forecast_MW',
        'Forecast_Error_MW', 'Forecast_Error_Pct',
        'AI_Error_MW', 'AI_Error_Pct',
        'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb', 'Capacity_MW'
    ]
    df = _clean_numeric(df_h.copy(), [c for c in num_cols if c in df_h.columns])
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df.dropna(subset=['Time']).sort_values('Time')

    _draw_ai_data_diagnostics(df)

    required_error_pct_cols = ['Forecast_Error_Pct', 'AI_Error_Pct']
    missing_error_cols = [c for c in required_error_pct_cols if c not in df.columns]
    if missing_error_cols:
        st.info("Недостатньо історичних даних для аналізу помилок прогнозу.")
        return

    # Беремо тільки години, де є факт генерації. Нічні нулі не повинні прикрашати точність.
    df_fact = df[(df['Fact_MW'] > 0.05) & (df['Forecast_MW'] > 0.05)].copy()
    if df_fact.empty:
        st.info("Недостатньо історичних даних для аналізу.")
        return

    df_fact['Base_Abs_Error_Pct'] = df_fact['Forecast_Error_Pct'].abs()
    df_fact['AI_Abs_Error_Pct'] = df_fact['AI_Error_Pct'].abs()

    df_errors = df_fact[
        (df_fact['Base_Abs_Error_Pct'] > 0) |
        (df_fact['AI_Abs_Error_Pct'] > 0)
    ].copy()
    if df_errors.empty:
        st.info("Недостатньо історичних даних для аналізу.")
        return

    base_mape = float(df_fact['Base_Abs_Error_Pct'].mean())
    ai_mape = float(df_fact['AI_Abs_Error_Pct'].mean())
    improvement_pct = 100 * (base_mape - ai_mape) / base_mape if base_mape > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("MAPE базового прогнозу", f"{base_mape:.1f}%")
    c2.metric("MAPE прогнозу ШІ", f"{ai_mape:.1f}%")
    c3.metric("Покращення ШІ", f"{improvement_pct:.1f}%")

    st.caption(
        "Це центр контролю якості ШІ: тут видно реальні помилки між базовим прогнозом, "
        "AI_Forecast_MW і фактом АСКОЕ. Повторне навчання виконує collector.py, не Streamlit."
    )

    st.write("---")

    # Денна статистика
    df_fact['Дата'] = df_fact['Time'].dt.date
    daily = df_fact.groupby('Дата').agg(
        **{
            'Факт (МВт·год)': ('Fact_MW', 'sum'),
            'Прогноз сайту (МВт·год)': ('Forecast_MW', 'sum'),
            'Прогноз ШІ (МВт·год)': ('AI_Forecast_MW', 'sum'),
            'MAPE сайту %': ('Base_Abs_Error_Pct', 'mean'),
            'MAPE ШІ %': ('AI_Abs_Error_Pct', 'mean')
        }
    ).reset_index().sort_values('Дата')

    daily['Покращення ШІ %'] = (
        100 * (
            daily['MAPE сайту %'] - daily['MAPE ШІ %']
        ) / daily['MAPE сайту %'].replace(0, pd.NA)
    ).fillna(0).round(1)

    for col in daily.columns:
        if col != 'Дата':
            daily[col] = pd.to_numeric(daily[col], errors='coerce').round(2)

    last_fact_time = pd.to_datetime(df_fact['Time'].max())
    now_kyiv = pd.Timestamp.now(tz='Europe/Kyiv').tz_localize(None)
    expected_lag_days = 2 if now_kyiv.hour < 9 else 1
    expected_latest_date = (now_kyiv.normalize() - pd.Timedelta(days=expected_lag_days)).date()
    latest_fact_date = last_fact_time.date()
    fact_age_hours = (now_kyiv - last_fact_time).total_seconds() / 3600

    if latest_fact_date < expected_latest_date:
        st.warning(
            f"Останній факт АСКОЕ у базі: {last_fact_time.strftime('%d.%m.%Y %H:%M')}. "
            f"Очікуваний останній звіт: {expected_latest_date.strftime('%d.%m.%Y')}. "
            "Перевірте ранковий автосинхронізатор або запустіть SkyGrid Auto Sync вручну."
        )
    elif fact_age_hours > 30:
        st.info(
            f"Останній факт АСКОЕ у базі: {last_fact_time.strftime('%d.%m.%Y %H:%M')}. "
            "Це нормально для ранкового вікна до обробки нового добового звіту."
        )

    def _quality_window(window_days):
        recent_quality = daily.tail(window_days).copy()
        if recent_quality.empty:
            return None
        base = float(recent_quality['MAPE сайту %'].mean())
        ai = float(recent_quality['MAPE ШІ %'].mean())
        improvement = 100 * (base - ai) / base if base > 0 else 0
        better_days = float((recent_quality['Покращення ШІ %'] > 0).mean() * 100)
        return base, ai, improvement, better_days, len(recent_quality)

    q7 = _quality_window(7)
    q30 = _quality_window(30)
    if q7 or q30:
        st.markdown("##### Операційний контроль якості прогнозу")
        c1, c2, c3, c4 = st.columns(4)
        if q7:
            c1.metric("MAPE ШІ за 7 днів", f"{q7[1]:.1f}%", f"{q7[2]:+.1f}% до сайту")
            c2.metric("Днів, де ШІ краще", f"{q7[3]:.0f}%", f"{q7[4]} дн.")
        if q30:
            c3.metric("MAPE ШІ за 30 днів", f"{q30[1]:.1f}%", f"{q30[2]:+.1f}% до сайту")
            c4.metric("Стабільність ШІ", f"{q30[3]:.0f}%", f"{q30[4]} дн.")

        if q7:
            if q7[2] >= 10 and q7[3] >= 60:
                st.success("Рекомендація: для найближчого добового планування ШІ зараз виглядає корисним орієнтиром, але фінальне рішення залишайте за оператором.")
            elif q7[2] <= -5 or q7[3] < 45:
                st.warning("Рекомендація: зараз базовий прогноз сайту виглядає надійнішим за ШІ. Використовуйте ШІ тільки як додаткову перевірку.")
            else:
                st.info("Рекомендація: ШІ і базовий прогноз близькі за якістю. Потрібна ручна оцінка з урахуванням погоди та виробничого контексту.")

        if q7 and q7[2] < -5:
            st.warning("За останні 7 днів ШІ погіршує прогноз відносно базового сайту. Варто перевірити факти, погоду або параметри моделі.")
        elif q7 and q7[2] > 5:
            st.success("За останні 7 днів ШІ помітно покращує прогноз відносно базового сайту.")
        else:
            st.info("За останні 7 днів ШІ близький до базового прогнозу. Використовуйте його як допоміжний орієнтир.")

        st.write("---")

    _draw_error_factor_analysis(df_fact)
    _draw_shadow_experiment(df_fact)

    st.markdown("##### Денний графік: факт vs прогноз сайту vs ШІ")
    recent_daily_energy = daily.tail(30)
    fig_daily = go.Figure()
    fig_daily.add_trace(go.Scatter(
        x=recent_daily_energy['Дата'], y=recent_daily_energy['Факт (МВт·год)'],
        name='Факт', mode='lines+markers',
        line=dict(color='#378ADD', width=2.5)
    ))
    fig_daily.add_trace(go.Scatter(
        x=recent_daily_energy['Дата'], y=recent_daily_energy['Прогноз сайту (МВт·год)'],
        name='Прогноз сайту', mode='lines+markers',
        line=dict(color='#D85A30', width=2, dash='dot')
    ))
    fig_daily.add_trace(go.Scatter(
        x=recent_daily_energy['Дата'], y=recent_daily_energy['Прогноз ШІ (МВт·год)'],
        name='Прогноз ШІ', mode='lines+markers',
        line=dict(color='#1D9E75', width=2, dash='dash')
    ))
    fig_daily.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='МВт·год'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        hovermode='x unified'
    )
    st.plotly_chart(fig_daily, width='stretch')

    st.write("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("##### Денна похибка: сайт vs ШІ")
        recent_daily = daily.tail(30)
        fig_err = go.Figure()
        fig_err.add_trace(go.Scatter(
            x=recent_daily['Дата'], y=recent_daily['MAPE сайту %'],
            name='MAPE сайту %', mode='lines+markers',
            line=dict(color='#D85A30', width=2, dash='dot')
        ))
        fig_err.add_trace(go.Scatter(
            x=recent_daily['Дата'], y=recent_daily['MAPE ШІ %'],
            name='MAPE ШІ %', mode='lines+markers',
            line=dict(color='#378ADD', width=2)
        ))
        fig_err.update_layout(
            height=260, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title='%'),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
            hovermode='x unified'
        )
        st.plotly_chart(fig_err, width='stretch')

    with col_right:
        st.markdown("##### Покращення ШІ по днях")
        recent_daily = daily.tail(30).copy()
        fig_impr = go.Figure()
        fig_impr.add_trace(go.Bar(
            x=recent_daily['Дата'], y=recent_daily['Покращення ШІ %'],
            name='Покращення ШІ %',
            marker_color=['#1D9E75' if v >= 0 else '#D85A30' for v in recent_daily['Покращення ШІ %']]
        ))
        fig_impr.add_hline(y=0, line_color='gray', line_width=1, line_dash='dot')
        fig_impr.update_layout(
            height=260, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title='%'), showlegend=False,
            hovermode='x unified'
        )
        st.plotly_chart(fig_impr, width='stretch')

    st.write("---")

    st.markdown("##### Факт vs прогноз сайту vs ШІ — погодинно, останні 5 днів з фактом")
    last_fact_time = df_fact['Time'].max()
    window_start = last_fact_time - pd.Timedelta(days=5)
    recent = df_fact[df_fact['Time'] >= window_start].copy()

    if recent.empty:
        st.info("Недостатньо погодинних даних для графіку.")
    else:
        fig_hourly = go.Figure()
        fig_hourly.add_trace(go.Scatter(
            x=recent['Time'], y=recent['Fact_MW'],
            name='Факт АСКОЕ', mode='lines',
            line=dict(color='#378ADD', width=2.5),
            fill='tozeroy', fillcolor='rgba(55,138,221,0.07)'
        ))
        fig_hourly.add_trace(go.Scatter(
            x=recent['Time'], y=recent['AI_Forecast_MW'],
            name='Прогноз ШІ', mode='lines',
            line=dict(color='#1D9E75', width=2, dash='dash')
        ))
        fig_hourly.add_trace(go.Scatter(
            x=recent['Time'], y=recent['Forecast_MW'],
            name='Прогноз сайту', mode='lines',
            line=dict(color='#D85A30', width=1.5, dash='dot')
        ))
        fig_hourly.update_layout(
            height=300, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title='МВт'),
            xaxis=dict(title='Час'),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
            hovermode='x unified'
        )
        st.plotly_chart(fig_hourly, width='stretch')

    st.write("---")

    st.markdown("##### Таблиця якості по днях")
    display = daily.sort_values('Дата', ascending=False).copy()
    st.dataframe(
        display.style.background_gradient(
            subset=['Покращення ШІ %'], cmap='RdYlGn', vmin=-30, vmax=30
        ),
        use_container_width=True,
        hide_index=True
    )


# ─────────────────────────────────────────────
#  ВКЛАДКА 2: БАЗА
# ─────────────────────────────────────────────

def draw_base_tab(df_h):
    st.markdown("##### 📅 Статистика по днях")

    if df_h.empty:
        st.info("База даних порожня.")
        return

    num_cols = ['Fact_MW', 'Forecast_MW']
    if 'AI_Forecast_MW' in df_h.columns:
        num_cols.append('AI_Forecast_MW')
    df = _clean_numeric(df_h.copy(), num_cols)
    df['Time'] = pd.to_datetime(df['Time'])
    df['Дата'] = df['Time'].dt.date

    agg = {}
    if 'Fact_MW' in df.columns:
        agg['Факт (МВт·год)'] = ('Fact_MW', 'sum')
    if 'Forecast_MW' in df.columns:
        agg['Прогноз сайту (МВт·год)'] = ('Forecast_MW', 'sum')
    if 'AI_Forecast_MW' in df.columns:
        agg['Прогноз ШІ (МВт·год)'] = ('AI_Forecast_MW', 'sum')

    if not agg:
        st.warning("Немає числових колонок для статистики.")
        return

    daily = df.groupby('Дата').agg(**agg).reset_index()
    daily = daily.sort_values('Дата', ascending=False)
    for col in daily.columns[1:]:
        daily[col] = daily[col].round(2)

    if 'Факт (МВт·год)' in daily.columns and 'Прогноз сайту (МВт·год)' in daily.columns:
        daily['Відхилення (МВт·год)'] = (daily['Факт (МВт·год)'] - daily['Прогноз сайту (МВт·год)']).round(2)
        daily['Точність %'] = (
            100 - (abs(daily['Відхилення (МВт·год)']) / daily['Факт (МВт·год)'].replace(0, 1) * 100)
        ).clip(0, 100).round(1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Днів у базі", f"{len(daily)}")
    if 'Факт (МВт·год)' in daily.columns:
        c2.metric("Всього факт", f"{daily['Факт (МВт·год)'].sum():.0f} МВт·год")
    if 'Точність %' in daily.columns:
        c3.metric("Середня точність", f"{daily['Точність %'].mean():.1f}%")

    st.write("---")

    fig = go.Figure()
    if 'Факт (МВт·год)' in daily.columns:
        fig.add_trace(go.Bar(
            x=daily['Дата'], y=daily['Факт (МВт·год)'],
            name='Факт', marker_color='#378ADD'
        ))
    if 'Прогноз ШІ (МВт·год)' in daily.columns:
        # Показуємо тільки дні де є AI_Forecast_MW > 0
        ai_daily = daily[daily['Прогноз ШІ (МВт·год)'] > 0]
        if not ai_daily.empty:
            fig.add_trace(go.Scatter(
                x=ai_daily['Дата'], y=ai_daily['Прогноз ШІ (МВт·год)'],
                name='Прогноз ШІ', mode='lines+markers',
                line=dict(color='#1D9E75', width=2),
                marker=dict(size=6)
            ))
    if 'Прогноз сайту (МВт·год)' in daily.columns:
        fig.add_trace(go.Scatter(
            x=daily['Дата'], y=daily['Прогноз сайту (МВт·год)'],
            name='Прогноз сайту', mode='lines+markers',
            line=dict(color='#D85A30', width=2, dash='dash'),
            marker=dict(size=4)
        ))
    fig.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='МВт·год'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        barmode='overlay',
        hovermode='x unified'
    )
    st.plotly_chart(fig, width='stretch')

    # Таблиця — показуємо тільки дні з фактом або прогнозом ШІ
    display = daily[daily['Факт (МВт·год)'] > 0].copy() if 'Факт (МВт·год)' in daily.columns else daily.copy()
    if not display.empty:
        st.dataframe(
            display.style.background_gradient(
                subset=['Точність %'] if 'Точність %' in display.columns else [],
                cmap='RdYlGn', vmin=50, vmax=100
            ),
            use_container_width=True,
            hide_index=True
        )


# ─────────────────────────────────────────────
#  ВКЛАДКА: ЖУРНАЛ КОНТРОЛЮ
# ─────────────────────────────────────────────

def _add_log_event(events, when, level, event_type, description, source, recommendation):
    events.append({
        'Дата/час': pd.to_datetime(when).strftime('%d.%m.%Y %H:%M') if pd.notna(when) else '',
        'Рівень': level,
        'Тип': event_type,
        'Опис': description,
        'Джерело': source,
        'Рекомендація': recommendation,
    })


def _daily_sum(df, day, value_col):
    if df is None or df.empty or value_col not in df.columns or 'Time' not in df.columns:
        return 0.0
    start = pd.Timestamp(day)
    end = start + pd.Timedelta(days=1)
    mask = (df['Time'] >= start) & (df['Time'] < end)
    return float(pd.to_numeric(df.loc[mask, value_col], errors='coerce').fillna(0).sum())


def _latest_time_with_value(df, value_col):
    if df is None or df.empty or value_col not in df.columns or 'Time' not in df.columns:
        return None
    values = pd.to_numeric(df[value_col], errors='coerce').fillna(0)
    valid = df[(values > 0.05) & df['Time'].notna()]
    if valid.empty:
        return None
    return pd.to_datetime(valid['Time']).max()


def _recent_daily_fact_median(df_h):
    if df_h is None or df_h.empty or 'Time' not in df_h.columns or 'Fact_MW' not in df_h.columns:
        return 0.0
    df = _clean_numeric(df_h.copy(), ['Fact_MW'])
    df['Time'] = pd.to_datetime(df['Time'], errors='coerce')
    df = df[(df['Fact_MW'] > 0.05) & df['Time'].notna()].copy()
    if df.empty:
        return 0.0
    df['Дата'] = df['Time'].dt.date
    daily = df.groupby('Дата')['Fact_MW'].sum().tail(14)
    return float(daily.median()) if not daily.empty else 0.0


def _build_control_log(df_h, df_f, df_open_meteo, now_ua):
    events = []
    now_ts = pd.Timestamp(now_ua).tz_localize(None) if getattr(now_ua, 'tzinfo', None) else pd.Timestamp(now_ua)
    tomorrow = (now_ts.normalize() + pd.Timedelta(days=1)).date()

    hist = df_h.copy() if df_h is not None else pd.DataFrame()
    if not hist.empty:
        hist['Time'] = pd.to_datetime(hist['Time'], errors='coerce')
        numeric_cols = [
            'Fact_MW', 'Forecast_MW', 'AI_Forecast_MW',
            'Forecast_Error_Pct', 'AI_Error_Pct'
        ]
        hist = _clean_numeric(hist, [c for c in numeric_cols if c in hist.columns])

    forecast = df_f.copy() if df_f is not None else pd.DataFrame()
    if not forecast.empty:
        forecast['Time'] = pd.to_datetime(forecast['Time'], errors='coerce')
        forecast = _clean_numeric(forecast, [c for c in ['AI_MW', 'Forecast_MW'] if c in forecast.columns])

    open_meteo = df_open_meteo.copy() if df_open_meteo is not None else pd.DataFrame()
    if not open_meteo.empty:
        open_meteo['Time'] = pd.to_datetime(open_meteo['Time'], errors='coerce')
        open_meteo = _clean_numeric(open_meteo, [c for c in ['Forecast_MW'] if c in open_meteo.columns])

    expected_lag_days = 2 if now_ts.hour < 9 else 1
    expected_latest_date = (now_ts.normalize() - pd.Timedelta(days=expected_lag_days)).date()
    last_fact_time = _latest_time_with_value(hist, 'Fact_MW')
    if last_fact_time is None:
        _add_log_event(
            events, now_ts, 'Критично', 'Немає факту',
            'У базі не знайдено фактичної генерації АСКОЕ.',
            'АСКОЕ / Google Sheets',
            'Перевірити імпорт листів FusionSolar та запуск SkyGrid Auto Sync.'
        )
    elif last_fact_time.date() < expected_latest_date:
        _add_log_event(
            events, now_ts, 'Попередження', 'Факт відстає',
            f"Останній факт АСКОЕ: {last_fact_time.strftime('%d.%m.%Y %H:%M')}; очікувався звіт за {expected_latest_date.strftime('%d.%m.%Y')}.",
            'АСКОЕ / Gmail',
            'Перевірити ранковий автосинхронізатор або запустити SkyGrid Auto Sync вручну.'
        )

    ai_tomorrow = _daily_sum(forecast, tomorrow, 'AI_MW')
    base_tomorrow = _daily_sum(forecast, tomorrow, 'Forecast_MW')
    recent_median = _recent_daily_fact_median(hist)
    if ai_tomorrow <= 0 and base_tomorrow > 0:
        _add_log_event(
            events, now_ts, 'Критично', 'Немає прогнозу ШІ',
            'На завтра є базовий прогноз, але немає збереженого прогнозу ШІ.',
            'AI_Forecast_MW',
            'Перевірити collector.py та останній успішний запуск GitHub Actions.'
        )
    elif ai_tomorrow > 0 and base_tomorrow > 0:
        gap = abs(ai_tomorrow - base_tomorrow) / max(ai_tomorrow, base_tomorrow) * 100
        if gap >= 45:
            _add_log_event(
                events, now_ts, 'Попередження', 'ШІ vs база',
                f"Прогноз ШІ на завтра ({ai_tomorrow:.1f} МВт·год) розходиться з базовим прогнозом ({base_tomorrow:.1f} МВт·год) на {gap:.0f}%.",
                'AI_Forecast_MW / Visual Crossing',
                'Перевірити метеоумови та не використовувати ШІ як єдине джерело рішення.'
            )

    if ai_tomorrow > 0 and recent_median > 0:
        if ai_tomorrow < recent_median * 0.35:
            _add_log_event(
                events, now_ts, 'Попередження', 'Нетипово низький прогноз',
                f"Прогноз ШІ на завтра {ai_tomorrow:.1f} МВт·год проти медіани останніх днів {recent_median:.1f} МВт·год.",
                'AI_Forecast_MW',
                'Перевірити хмарність, опади та коректність прогнозу інсоляції.'
            )
        elif ai_tomorrow > recent_median * 1.8:
            _add_log_event(
                events, now_ts, 'Інфо', 'Нетипово високий прогноз',
                f"Прогноз ШІ на завтра {ai_tomorrow:.1f} МВт·год суттєво вище медіани останніх днів {recent_median:.1f} МВт·год.",
                'AI_Forecast_MW',
                'Звірити з погодою та поточною встановленою потужністю СЕС.'
            )

    om_tomorrow = _daily_sum(open_meteo, tomorrow, 'Forecast_MW')
    if om_tomorrow > 0 and base_tomorrow > 0:
        meteo_gap = abs(om_tomorrow - base_tomorrow) / max(om_tomorrow, base_tomorrow) * 100
        if meteo_gap >= 35:
            _add_log_event(
                events, now_ts, 'Попередження', 'Розбіжність метеоджерел',
                f"Visual Crossing і Open-Meteo для завтра розходяться на {meteo_gap:.0f}%.",
                'Visual Crossing / Open-Meteo',
                'Вважати прогноз метеоризиковим і перевірити добовий графік вручну.'
            )
    elif open_meteo.empty:
        _add_log_event(
            events, now_ts, 'Інфо', 'Open-Meteo недоступний',
            'Альтернативне метеоджерело зараз недоступне для контролю.',
            'Open-Meteo',
            'Основний прогноз працює, але контроль метеоризику обмежений.'
        )

    if not hist.empty and {'Time', 'Fact_MW', 'Forecast_MW', 'AI_Forecast_MW'}.issubset(hist.columns):
        daylight = hist[(hist['Fact_MW'] > 0.05) & (hist['Forecast_MW'] > 0.05)].copy()
        if not daylight.empty:
            daylight['Дата'] = daylight['Time'].dt.date
            daily = daylight.groupby('Дата').agg(
                fact_mwh=('Fact_MW', 'sum'),
                base_mwh=('Forecast_MW', 'sum'),
                ai_mwh=('AI_Forecast_MW', 'sum'),
            ).reset_index().tail(30)
            for _, row in daily.iterrows():
                fact = float(row['fact_mwh'])
                if fact <= 0:
                    continue
                base_err = abs(float(row['base_mwh']) - fact) / fact * 100
                ai_err = abs(float(row['ai_mwh']) - fact) / fact * 100
                event_time = pd.Timestamp(row['Дата'])
                if ai_err >= 60:
                    _add_log_event(
                        events, event_time, 'Попередження', 'Висока помилка ШІ',
                        f"Добова помилка ШІ {ai_err:.0f}% при факті {fact:.1f} МВт·год.",
                        'Історія прогнозів',
                        'Проаналізувати погодні умови цього дня та параметри моделі.'
                    )
                if ai_err > base_err + 15:
                    _add_log_event(
                        events, event_time, 'Інфо', 'ШІ гірший за базу',
                        f"ШІ був гірший за базовий прогноз: {ai_err:.0f}% проти {base_err:.0f}%.",
                        'Історія прогнозів',
                        'Використати день як кандидат для розбору похибки моделі.'
                    )

    if not events:
        _add_log_event(
            events, now_ts, 'Інфо', 'Без критичних подій',
            'За поточними правилами журналу суттєвих проблем не знайдено.',
            'SkyGrid Control',
            'Продовжувати накопичення історії та моніторинг якості прогнозу.'
        )

    return pd.DataFrame(events)


def draw_control_log_tab(df_h, df_f, df_open_meteo, now_ua):
    st.markdown("##### Журнал контролю прогнозу")
    st.caption(
        "Read-only журнал: події формуються з поточного стану даних та останньої історії. "
        "Поки що він нічого не записує в Google Sheets."
    )

    log_df = _build_control_log(df_h, df_f, df_open_meteo, now_ua)
    severity_order = {'Критично': 0, 'Попередження': 1, 'Інфо': 2}
    log_df['_order'] = log_df['Рівень'].map(severity_order).fillna(3)
    log_df['_time'] = pd.to_datetime(log_df['Дата/час'], format='%d.%m.%Y %H:%M', errors='coerce')
    log_df = log_df.sort_values(['_order', '_time'], ascending=[True, False]).drop(columns=['_order', '_time'])

    c1, c2, c3 = st.columns(3)
    c1.metric("Критичні", int((log_df['Рівень'] == 'Критично').sum()))
    c2.metric("Попередження", int((log_df['Рівень'] == 'Попередження').sum()))
    c3.metric("Інформаційні", int((log_df['Рівень'] == 'Інфо').sum()))

    st.dataframe(log_df, use_container_width=True, hide_index=True)


def draw_meteo_tab(df_f, df_open_meteo=None):
    col_title, col_src = st.columns([6, 2])
    with col_title:
        st.markdown("##### 🌤 Метеоаналіз — прогноз на 5 днів")
    with col_src:
        st.markdown(
            """
            <style>
            .meteo-source-attribution {
                display: flex;
                align-items: center;
                justify-content: flex-end;
                flex-wrap: wrap;
                gap: 8px;
                padding-top: 2px;
                color: rgba(255,255,255,0.48);
                font-size: 12px;
            }
            .meteo-source-attribution__label {
                color: rgba(255,255,255,0.48);
                white-space: nowrap;
            }
            .meteo-source-chip {
                display: inline-flex;
                align-items: center;
                gap: 7px;
                padding: 6px 10px;
                border-radius: 999px;
                border: 1px solid rgba(255,255,255,0.10);
                background: rgba(255,255,255,0.035);
                color: rgba(255,255,255,0.86) !important;
                text-decoration: none !important;
                font-weight: 700;
                line-height: 1;
            }
            .meteo-source-chip:hover {
                border-color: rgba(255,184,0,0.36);
                background: rgba(255,184,0,0.08);
                color: #ffffff !important;
            }
            .meteo-source-chip__mark {
                width: 18px;
                height: 18px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 10px;
                font-weight: 900;
            }
            .meteo-source-chip__mark--vc {
                background: rgba(255,184,0,0.16);
                color: #ffb800;
            }
            .meteo-source-chip__mark--om {
                background: rgba(0,229,255,0.14);
                color: #00e5ff;
            }
            .meteo-provider-row {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 12px;
                margin: 8px 0 18px;
            }
            .meteo-provider-card {
                display: block;
                min-height: 72px;
                padding: 14px 16px;
                border-radius: 8px;
                border: 1px solid rgba(255,255,255,0.10);
                background: linear-gradient(135deg, rgba(17,22,34,0.96), rgba(10,15,24,0.98));
                color: rgba(255,255,255,0.88) !important;
                text-decoration: none !important;
                box-shadow: 0 12px 26px rgba(0,0,0,0.24);
            }
            .meteo-provider-card:hover {
                border-color: var(--provider-accent);
                background: linear-gradient(135deg, rgba(22,28,40,0.98), rgba(10,15,24,0.98));
            }
            .meteo-provider-card__top {
                display: flex;
                align-items: center;
                gap: 9px;
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
            }
            .meteo-provider-card__mark {
                width: 24px;
                height: 24px;
                border-radius: 999px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--provider-bg);
                color: var(--provider-accent);
                font-size: 11px;
                font-weight: 900;
            }
            .meteo-provider-card__hint {
                margin-top: 7px;
                color: rgba(255,255,255,0.52);
                font-size: 12px;
            }
            </style>
            <div class="meteo-source-attribution">
                <span class="meteo-source-attribution__label">Джерела:</span>
                <a class="meteo-source-chip" href="https://www.visualcrossing.com/" target="_blank" rel="noopener noreferrer">
                    <span class="meteo-source-chip__mark meteo-source-chip__mark--vc">VC</span>
                    Visual Crossing
                </a>
                <a class="meteo-source-chip" href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">
                    <span class="meteo-source-chip__mark meteo-source-chip__mark--om">OM</span>
                    Open-Meteo
                </a>
            </div>
            """,
            unsafe_allow_html=True
        )

    if df_f.empty:
        st.info("Метеодані недоступні.")
        return

    df = df_f.copy()
    df['Time'] = pd.to_datetime(df['Time'])
    cutoff = df['Time'].min() + pd.Timedelta(days=5)
    df = df[df['Time'] <= cutoff]

    df_alt = pd.DataFrame()
    if df_open_meteo is not None and not df_open_meteo.empty:
        df_alt = df_open_meteo.copy()
        df_alt['Time'] = pd.to_datetime(df_alt['Time'])
        df_alt = df_alt[(df_alt['Time'] >= df['Time'].min()) & (df_alt['Time'] <= cutoff)]

    row = df.iloc[0] if not df.empty else None
    if row is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🌡 Температура",   f"{row.get('Temp', 0):.1f} °C")
        c2.metric("☁️ Хмарність",     f"{row.get('CloudCover', 0):.0f} %")
        c3.metric("💨 Вітер",         f"{row.get('WindSpeed', 0):.1f} м/с")
        c4.metric("🌧 Опади (імов.)", f"{row.get('PrecipProb', 0):.0f} %")

    st.write("---")

    if not df_alt.empty:
        st.markdown("##### Порівняння метеоджерел (режим спостереження)")
        st.markdown(
            """
            <div class="meteo-provider-row">
                <a class="meteo-provider-card" style="--provider-accent:#ffb800;--provider-bg:rgba(255,184,0,0.16);" href="https://www.visualcrossing.com/" target="_blank" rel="noopener noreferrer">
                    <div class="meteo-provider-card__top">
                        <span class="meteo-provider-card__mark">VC</span>
                        Visual Crossing
                    </div>
                    <div class="meteo-provider-card__hint">Основне джерело погодного прогнозу для розрахунку генерації.</div>
                </a>
                <a class="meteo-provider-card" style="--provider-accent:#00e5ff;--provider-bg:rgba(0,229,255,0.14);" href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">
                    <div class="meteo-provider-card__top">
                        <span class="meteo-provider-card__mark">OM</span>
                        Open-Meteo
                    </div>
                    <div class="meteo-provider-card__hint">Альтернативне відкрите джерело для контролю метеоризику.</div>
                </a>
            </div>
            """,
            unsafe_allow_html=True
        )

        vc_daily = df.groupby(df['Time'].dt.date).agg(
            VC_MWh=('Forecast_MW', 'sum'),
            VC_Rad=('Rad', 'sum'),
            VC_Cloud=('CloudCover', 'mean')
        ).reset_index().rename(columns={'Time': 'Дата'})
        om_daily = df_alt.groupby(df_alt['Time'].dt.date).agg(
            OM_MWh=('Forecast_MW', 'sum'),
            OM_Rad=('Rad', 'sum'),
            OM_Cloud=('CloudCover', 'mean')
        ).reset_index().rename(columns={'Time': 'Дата'})
        compare = vc_daily.merge(om_daily, on='Дата', how='inner').head(5)

        if not compare.empty:
            compare['Різниця МВт·год'] = compare['OM_MWh'] - compare['VC_MWh']
            compare['Розбіжність %'] = (
                compare['Різниця МВт·год'].abs() /
                compare[['VC_MWh', 'OM_MWh']].max(axis=1).replace(0, pd.NA) * 100
            ).fillna(0)
            compare['Різниця хмарності, п.п.'] = compare['OM_Cloud'] - compare['VC_Cloud']

            next3 = compare.head(3)
            vc_sum = float(next3['VC_MWh'].sum())
            om_sum = float(next3['OM_MWh'].sum())
            max_divergence = float(next3['Розбіжність %'].max())
            cloud_gap = float(next3['Різниця хмарності, п.п.'].abs().max())

            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.markdown(
                    f"""
                    <a class="meteo-provider-card" style="--provider-accent:#ffb800;--provider-bg:rgba(255,184,0,0.16);min-height:96px;" href="https://www.visualcrossing.com/" target="_blank" rel="noopener noreferrer">
                        <div class="meteo-provider-card__top"><span class="meteo-provider-card__mark">VC</span>Visual Crossing, 3 дні</div>
                        <div style="margin-top:10px;color:#ffffff;font-size:31px;line-height:1.1;font-weight:500;">{vc_sum:.1f} МВт·год</div>
                    </a>
                    """,
                    unsafe_allow_html=True
                )
            with c2:
                st.markdown(
                    f"""
                    <a class="meteo-provider-card" style="--provider-accent:#00e5ff;--provider-bg:rgba(0,229,255,0.14);min-height:96px;" href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">
                        <div class="meteo-provider-card__top"><span class="meteo-provider-card__mark">OM</span>Open-Meteo, 3 дні</div>
                        <div style="margin-top:10px;color:#ffffff;font-size:31px;line-height:1.1;font-weight:500;">{om_sum:.1f} МВт·год</div>
                    </a>
                    """,
                    unsafe_allow_html=True
                )
            c3.metric("Макс. розбіжність", f"{max_divergence:.0f}%")
            c4.metric("Різниця хмарності", f"{cloud_gap:.0f} п.п.")

            if max_divergence >= 35 or cloud_gap >= 35:
                st.warning(
                    "Метеоджерела суттєво розходяться. Фінальний прогноз поки не змінено, "
                    "але для оператора цей період варто вважати метеоризиком."
                )
            else:
                st.success("Метеоджерела загалом узгоджуються для найближчих днів.")

            fig_cmp = go.Figure()
            fig_cmp.add_trace(go.Bar(
                x=compare['Дата'], y=compare['VC_MWh'],
                name='Visual Crossing', marker_color='rgba(255,184,0,0.72)'
            ))
            fig_cmp.add_trace(go.Bar(
                x=compare['Дата'], y=compare['OM_MWh'],
                name='Open-Meteo', marker_color='rgba(0,229,255,0.62)'
            ))
            fig_cmp.update_layout(
                height=250, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(title='МВт·год'),
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
                barmode='group',
                hovermode='x unified'
            )
            st.plotly_chart(fig_cmp, width='stretch')

            table = compare.copy()
            table['Дата'] = pd.to_datetime(table['Дата']).dt.strftime('%d.%m')
            table = table.rename(columns={
                'VC_MWh': 'Visual Crossing, МВт·год',
                'OM_MWh': 'Open-Meteo, МВт·год',
                'VC_Cloud': 'Хмарність VC, %',
                'OM_Cloud': 'Хмарність OM, %'
            })
            display_cols = [
                'Дата', 'Visual Crossing, МВт·год', 'Open-Meteo, МВт·год',
                'Різниця МВт·год', 'Розбіжність %',
                'Хмарність VC, %', 'Хмарність OM, %', 'Різниця хмарності, п.п.'
            ]
            st.dataframe(
                table[display_cols].round(1),
                use_container_width=True,
                hide_index=True
            )

            st.caption(
                "Open-Meteo зараз використовується тільки для контролю метеоризику. "
                "Основний прогноз і навчання моделі не змінені."
            )
    else:
        st.info("Open-Meteo поки недоступний. Основний метеопрогноз Visual Crossing працює без змін.")

    st.write("---")

    st.markdown("##### Сонячна радіація та хмарність")
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    fig1.add_trace(go.Scatter(
        x=df['Time'], y=df['Rad'],
        name='Радіація VC (Вт/м²)', mode='lines',
        line=dict(color='#BA7517', width=2),
        fill='tozeroy', fillcolor='rgba(186,117,23,0.1)'
    ), secondary_y=False)
    if not df_alt.empty and 'Rad' in df_alt.columns:
        fig1.add_trace(go.Scatter(
            x=df_alt['Time'], y=df_alt['Rad'],
            name='Радіація OM (Вт/м²)', mode='lines',
            line=dict(color='#00e5ff', width=1.8)
        ), secondary_y=False)
    if 'CloudCover' in df.columns:
        fig1.add_trace(go.Scatter(
            x=df['Time'], y=df['CloudCover'],
            name='Хмарність VC (%)', mode='lines',
            line=dict(color='#888780', width=1.5, dash='dot')
        ), secondary_y=True)
    if not df_alt.empty and 'CloudCover' in df_alt.columns:
        fig1.add_trace(go.Scatter(
            x=df_alt['Time'], y=df_alt['CloudCover'],
            name='Хмарність OM (%)', mode='lines',
            line=dict(color='#7dd3fc', width=1.4, dash='dash')
        ), secondary_y=True)
    fig1.update_layout(
        height=220, margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        hovermode='x unified'
    )
    fig1.update_yaxes(title_text="Вт/м²", secondary_y=False)
    fig1.update_yaxes(title_text="%", secondary_y=True)
    st.plotly_chart(fig1, width='stretch')

    st.markdown("##### Температура повітря")
    fig2 = go.Figure(go.Scatter(
        x=df['Time'], y=df['Temp'],
        mode='lines', line=dict(color='#D85A30', width=2),
        fill='tozeroy', fillcolor='rgba(216,90,48,0.07)'
    ))
    fig2.update_layout(
        height=180, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='°C'), showlegend=False, hovermode='x unified'
    )
    st.plotly_chart(fig2, width='stretch')

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("##### Швидкість вітру")
        if 'WindSpeed' in df.columns:
            fig3 = go.Figure(go.Bar(
                x=df['Time'], y=df['WindSpeed'], marker_color='#378ADD'
            ))
            fig3.update_layout(
                height=180, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(title='м/с'), showlegend=False
            )
            st.plotly_chart(fig3, width='stretch')
        else:
            st.info("Дані про вітер відсутні.")

    with col_r:
        st.markdown("##### Імовірність опадів")
        if 'PrecipProb' in df.columns:
            fig4 = go.Figure(go.Bar(
                x=df['Time'], y=df['PrecipProb'], marker_color='#1D9E75'
            ))
            fig4.update_layout(
                height=180, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(title='%', range=[0, 100]), showlegend=False
            )
            st.plotly_chart(fig4, width='stretch')
        else:
            st.info("Дані про опади відсутні.")


# ─────────────────────────────────────────────
#  ВКЛАДКА 4: ПЛАН
# ─────────────────────────────────────────────

def draw_plan_tab(df_h, df_f, df_plan, now_ua):
    import plotly.graph_objects as go
    import pandas as pd

    month_names = {
        1: 'Січень', 2: 'Лютий', 3: 'Березень', 4: 'Квітень',
        5: 'Травень', 6: 'Червень', 7: 'Липень', 8: 'Серпень',
        9: 'Вересень', 10: 'Жовтень', 11: 'Листопад', 12: 'Грудень'
    }

    col_t, col_s = st.columns([6, 2])
    with col_t:
        st.markdown(f"##### 📋 План генерації vs Факт АСКОЕ vs ШІ — {month_names[now_ua.month]} {now_ua.year}")
    with col_s:
        st.markdown(
            "<div style='text-align:right; padding-top:6px; font-size:12px; color:gray;'>"
            "Джерело плану: Генерація СЕС (Google Sheets)"
            "</div>",
            unsafe_allow_html=True
        )

    if df_plan.empty:
        st.warning("⚠️ Дані плану недоступні. Перевірте доступ до таблиці.")
        return

    # --- Метрики місяця ---
    plan_month = df_plan.copy()
    plan_month['Дата'] = plan_month['Time'].dt.date

    # Факт за цей місяць
    df_h2 = df_h.copy()
    df_h2['Time'] = pd.to_datetime(df_h2['Time'])
    df_h2['Fact_MW'] = pd.to_numeric(
        df_h2['Fact_MW'].astype(str).str.replace(',', '.'), errors='coerce'
    ).fillna(0)
    fact_month = df_h2[
        (df_h2['Time'].dt.month == now_ua.month) &
        (df_h2['Time'].dt.year == now_ua.year) &
        (df_h2['Fact_MW'] > 0)
    ]

    plan_total = plan_month['Plan_MW'].sum()
    fact_total = fact_month['Fact_MW'].sum() if not fact_month.empty else 0
    days_with_fact = fact_month['Time'].dt.date.nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📋 План місяця", f"{plan_total:.0f} МВт·год")
    c2.metric("⚡ Факт (накопич.)", f"{fact_total:.1f} МВт·год")
    c3.metric("📊 Виконання", f"{(fact_total/plan_total*100):.1f}%" if plan_total > 0 else "—")
    c4.metric("📅 Днів з фактом", f"{days_with_fact}")

    st.write("---")

    # --- Датепікер для аналізу ---
    col_h1, col_h2 = st.columns([4, 1])
    with col_h1:
        st.markdown("##### Погодинний аналіз якості")
    with col_h2:
        # Визначаємо доступні дати де є факт
        available_dates = sorted(fact_month['Time'].dt.date.unique(), reverse=True)
        if not available_dates:
            st.info("Немає даних факту за поточний місяць.")
            return
        selected_date = st.date_input(
            "Дата аналізу",
            value=available_dates[0],
            min_value=available_dates[-1],
            max_value=available_dates[0],
            key="plan_date"
        )

    sel_ts = pd.Timestamp(selected_date)
    sel_ts_end = sel_ts + pd.Timedelta(days=1)

    fact_day  = fact_month[(fact_month['Time'] >= sel_ts) & (fact_month['Time'] < sel_ts_end)][['Time','Fact_MW']].copy()
    plan_day  = plan_month[(plan_month['Time'] >= sel_ts) & (plan_month['Time'] < sel_ts_end)][['Time','Plan_MW']].copy()

    # AI_Forecast_MW з df_h (прогноз ШІ збережений collector.py)
    df_h2_copy = df_h.copy()
    df_h2_copy['Time'] = pd.to_datetime(df_h2_copy['Time'])
    if 'AI_Forecast_MW' in df_h2_copy.columns:
        df_h2_copy['AI_Forecast_MW'] = pd.to_numeric(df_h2_copy['AI_Forecast_MW'].astype(str).str.replace(',','.'), errors='coerce').fillna(0)
        ai_day = df_h2_copy[(df_h2_copy['Time'] >= sel_ts) & (df_h2_copy['Time'] < sel_ts_end) & (df_h2_copy['AI_Forecast_MW'] > 0)][['Time','AI_Forecast_MW']].copy()
    else:
        ai_day = pd.DataFrame()

    if fact_day.empty:
        st.info(f"Немає даних факту за {selected_date.strftime('%d.%m.%Y')}.")
        return

    # --- Графік 1: абсолютні значення ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fact_day['Time'], y=fact_day['Fact_MW'],
        name='Факт АСКОЕ', mode='lines+markers',
        line=dict(color='#378ADD', width=2.5),
        fill='tozeroy', fillcolor='rgba(55,138,221,0.08)',
        marker=dict(size=5)
    ))
    if not ai_day.empty:
        fig.add_trace(go.Scatter(
            x=ai_day['Time'], y=ai_day['AI_Forecast_MW'],
            name='Прогноз ШІ', mode='lines+markers',
            line=dict(color='#1D9E75', width=2, dash='dash'),
            marker=dict(size=4)
        ))
    if not plan_day.empty:
        fig.add_trace(go.Scatter(
            x=plan_day['Time'], y=plan_day['Plan_MW'],
            name='План (замовлення)', mode='lines+markers',
            line=dict(color='#D85A30', width=2, dash='dot'),
            marker=dict(size=4)
        ))
    fig.update_layout(
        height=260, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='МВт'),
        xaxis=dict(tickformat='%H:%M'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        hovermode='x unified',
        title=dict(text=f"📅 {selected_date.strftime('%d.%m.%Y')}", x=0.5, font=dict(size=13))
    )
    st.plotly_chart(fig, width='stretch')

    # --- Графік 2: відхилення по годинах ---
    st.markdown("##### Відхилення від плану замовлення по годинах (МВт)")

    if not plan_day.empty:
        dev = fact_day.merge(plan_day, on='Time', how='inner')
        dev['Δ Факт−План'] = (dev['Fact_MW'] - dev['Plan_MW']).round(3)
        dev['Година'] = dev['Time'].dt.strftime('%H:00')
        colors = ['#378ADD' if v >= 0 else '#D85A30' for v in dev['Δ Факт−План']]

        fig_dev = go.Figure()
        fig_dev.add_trace(go.Bar(
            x=dev['Година'], y=dev['Δ Факт−План'],
            name='Факт − План', marker_color=colors, opacity=0.85,
            text=dev['Δ Факт−План'].apply(lambda v: f"+{v:.2f}" if v >= 0 else f"{v:.2f}"),
            textposition='outside', textfont=dict(size=10)
        ))

        if not ai_day.empty:
            dev_ai = plan_day.merge(ai_day, on='Time', how='inner')
            dev_ai['Δ ШІ−План'] = (dev_ai['AI_Forecast_MW'] - dev_ai['Plan_MW']).round(3)
            dev_ai['Година'] = dev_ai['Time'].dt.strftime('%H:00')
            fig_dev.add_trace(go.Scatter(
                x=dev_ai['Година'], y=dev_ai['Δ ШІ−План'],
                name='ШІ − План', mode='lines+markers',
                line=dict(color='#1D9E75', width=2),
                marker=dict(size=6)
            ))

        fig_dev.add_hline(y=0, line_color='gray', line_width=1, line_dash='dot')
        fig_dev.update_layout(
            height=280, margin=dict(l=0, r=0, t=20, b=40),
            yaxis=dict(title='МВт відхилення', zeroline=True),
            xaxis=dict(tickangle=-45, tickfont=dict(size=11)),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
            hovermode='x unified'
        )
        st.plotly_chart(fig_dev, width='stretch')

        # Підсумок
        col_s1, col_s2, col_s3 = st.columns(3)
        col_s1.metric("Серед. відхилення", f"{dev['Δ Факт−План'].mean():.3f} МВт")
        col_s2.metric("Макс. перевищення", f"+{dev['Δ Факт−План'].max():.3f} МВт")
        col_s3.metric("Макс. недовиконання", f"{dev['Δ Факт−План'].min():.3f} МВт")
    else:
        st.info("Немає даних плану за цю дату.")

    # ── ДРУГА ГРУПА: Замовлення vs Прогноз ШІ ──
    st.write("---")

    # AI_Forecast_MW з df_h
    df_h_ai = df_h.copy()
    df_h_ai['Time'] = pd.to_datetime(df_h_ai['Time'])
    if 'AI_Forecast_MW' in df_h_ai.columns:
        df_h_ai['AI_Forecast_MW'] = pd.to_numeric(
            df_h_ai['AI_Forecast_MW'].astype(str).str.replace(',', '.'),
            errors='coerce'
        ).fillna(0)
        ai_fc_day = df_h_ai[
            (df_h_ai['Time'] >= sel_ts) &
            (df_h_ai['Time'] < sel_ts_end) &
            (df_h_ai['AI_Forecast_MW'] > 0)
        ][['Time', 'AI_Forecast_MW']].copy()
    else:
        ai_fc_day = pd.DataFrame()

    if ai_fc_day.empty:
        st.info(f"⏳ Прогноз ШІ на {selected_date.strftime('%d.%m.%Y')} ще не збережено — він фіксується о 8:00 напередодні.")
    else:
        st.markdown(f"##### Замовлення vs Прогноз ШІ — {selected_date.strftime('%d.%m.%Y')}")

        # Графік: абсолютні значення
        fig_ai = go.Figure()
        if not plan_day.empty:
            fig_ai.add_trace(go.Scatter(
                x=plan_day['Time'], y=plan_day['Plan_MW'],
                name='План (замовлення)', mode='lines+markers',
                line=dict(color='#D85A30', width=2, dash='dot'),
                marker=dict(size=4)
            ))
        fig_ai.add_trace(go.Scatter(
            x=ai_fc_day['Time'], y=ai_fc_day['AI_Forecast_MW'],
            name='Прогноз ШІ (о 8:00)', mode='lines+markers',
            line=dict(color='#1D9E75', width=2.5),
            fill='tozeroy', fillcolor='rgba(29,158,117,0.07)',
            marker=dict(size=5)
        ))
        fig_ai.update_layout(
            height=260, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title='МВт'),
            xaxis=dict(tickformat='%H:%M'),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
            hovermode='x unified'
        )
        st.plotly_chart(fig_ai, width='stretch')

        # Графік відхилень ШІ від плану
        st.markdown("##### Відхилення прогнозу ШІ від плану замовлення по годинах (МВт)")

        if not plan_day.empty:
            dev_ai2 = plan_day.merge(ai_fc_day, on='Time', how='inner')
            dev_ai2['Δ ШІ−План'] = (dev_ai2['AI_Forecast_MW'] - dev_ai2['Plan_MW']).round(3)
            dev_ai2['Година'] = dev_ai2['Time'].dt.strftime('%H:00')
            colors_ai = ['#1D9E75' if v >= 0 else '#D85A30' for v in dev_ai2['Δ ШІ−План']]

            fig_dev_ai = go.Figure()
            fig_dev_ai.add_trace(go.Bar(
                x=dev_ai2['Година'], y=dev_ai2['Δ ШІ−План'],
                name='ШІ − План', marker_color=colors_ai, opacity=0.85,
                text=dev_ai2['Δ ШІ−План'].apply(lambda v: f"+{v:.2f}" if v >= 0 else f"{v:.2f}"),
                textposition='outside', textfont=dict(size=10)
            ))
            fig_dev_ai.add_hline(y=0, line_color='gray', line_width=1, line_dash='dot')
            fig_dev_ai.update_layout(
                height=280, margin=dict(l=0, r=0, t=20, b=40),
                yaxis=dict(title='МВт відхилення', zeroline=True),
                xaxis=dict(tickangle=-45, tickfont=dict(size=11)),
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
                hovermode='x unified'
            )
            st.plotly_chart(fig_dev_ai, width='stretch')

            # Підсумок
            col_a1, col_a2, col_a3 = st.columns(3)
            col_a1.metric("Серед. відхилення ШІ", f"{dev_ai2['Δ ШІ−План'].mean():.3f} МВт")
            col_a2.metric("Макс. перевищення ШІ", f"+{dev_ai2['Δ ШІ−План'].max():.3f} МВт")
            col_a3.metric("Макс. недовиконання ШІ", f"{dev_ai2['Δ ШІ−План'].min():.3f} МВт")

    st.write("---")

    # --- Денна статистика по місяцю ---
    st.markdown("##### Денне порівняння по місяцю (МВт·год/день)")

    plan_daily = plan_month.groupby('Дата')['Plan_MW'].sum().reset_index()
    plan_daily.columns = ['Дата', 'План (МВт·год)']

    if not fact_month.empty:
        fact_daily = fact_month.copy()
        fact_daily['Дата'] = fact_daily['Time'].dt.date
        fact_daily = fact_daily.groupby('Дата')['Fact_MW'].sum().reset_index()
        fact_daily.columns = ['Дата', 'Факт (МВт·год)']
        daily = plan_daily.merge(fact_daily, on='Дата', how='left').fillna(0)
    else:
        daily = plan_daily.copy()
        daily['Факт (МВт·год)'] = 0

    daily['Відхилення'] = (daily['Факт (МВт·год)'] - daily['План (МВт·год)']).round(2)
    daily['Виконання %'] = (
        daily['Факт (МВт·год)'] / daily['План (МВт·год)'].replace(0, 1) * 100
    ).clip(0, 150).round(1)

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(
        x=daily['Дата'], y=daily['План (МВт·год)'],
        name='План', marker_color='rgba(216,90,48,0.4)'
    ))
    fig2.add_trace(go.Bar(
        x=daily['Дата'], y=daily['Факт (МВт·год)'],
        name='Факт', marker_color='#378ADD'
    ))
    fig2.update_layout(
        height=280, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='МВт·год'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        barmode='overlay'
    )
    st.plotly_chart(fig2, width='stretch')

    # Таблиця
    display = daily[daily['Факт (МВт·год)'] > 0].copy()
    if not display.empty:
        st.dataframe(
            display.style.background_gradient(
                subset=['Виконання %'], cmap='RdYlGn', vmin=70, vmax=120
            ),
            use_container_width=True,
            hide_index=True
        )
