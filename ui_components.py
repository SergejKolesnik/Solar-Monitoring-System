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

    error_cols = ['Forecast_Error_MW', 'Forecast_Error_Pct', 'AI_Error_MW', 'AI_Error_Pct']
    required_error_pct_cols = ['Forecast_Error_Pct', 'AI_Error_Pct']
    missing_error_cols = [c for c in required_error_pct_cols if c not in df_h.columns]
    if missing_error_cols:
        st.info("Недостатньо історичних даних для аналізу.")
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
def draw_meteo_tab(df_f, df_open_meteo=None):
    col_title, col_src = st.columns([6, 2])
    with col_title:
        st.markdown("##### 🌤 Метеоаналіз — прогноз на 5 днів")
    with col_src:
        st.markdown(
            "<div style='text-align:right; padding-top:6px; font-size:12px; color:gray;'>"
            "Дані: Visual Crossing + Open-Meteo"
            "</div>",
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
            c1.metric("Visual Crossing, 3 дні", f"{vc_sum:.1f} МВт·год")
            c2.metric("Open-Meteo, 3 дні", f"{om_sum:.1f} МВт·год")
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
