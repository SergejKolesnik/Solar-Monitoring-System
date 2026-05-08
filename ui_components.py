import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _clean_numeric(df, columns):
    """Конвертуємо числові колонки — виправляє порожні рядки та текст з Google Sheets."""
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
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────
#  ВКЛАДКА 1: НАВЧАННЯ
# ─────────────────────────────────────────────

def draw_training_tab(df_h, accuracy_r2, importance, scatter_data, mse_error, comparison_df):

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("R² (тест)",        f"{accuracy_r2:.1f}%")
    c2.metric("MSE похибка",       f"{mse_error:.4f}")
    c3.metric("Записів у базі",    f"{len(df_h):,}")
    c4.metric("Активних факторів", len(importance) if importance is not None else 0)

    st.write("---")
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("##### Як R² росте з кількістю даних")
        if len(df_h) >= 20:
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.metrics import r2_score
            from sklearn.model_selection import train_test_split

            features = [c for c in ['Forecast_MW','CloudCover','Temp','WindSpeed','PrecipProb'] if c in df_h.columns]

            # Очищуємо від порожніх рядків Google Sheets
            df_h2 = _clean_numeric(df_h, features + ['Fact_MW'])
            df_clean = df_h2[df_h2['Fact_MW'] > 0].dropna(subset=['Fact_MW', features[0]])
            steps = list(range(20, len(df_clean), max(1, len(df_clean) // 15))) + [len(df_clean)]

            r2_values, sizes = [], []
            for n in steps:
                subset = df_clean.iloc[:n]
                if len(subset) < 20:
                    continue
                X = subset[features].fillna(0).astype(float)
                y = subset['Fact_MW'].astype(float)
                try:
                    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
                    m = RandomForestRegressor(n_estimators=30, random_state=42)
                    m.fit(X_tr, y_tr)
                    r2_values.append(round(r2_score(y_te, m.predict(X_te)) * 100, 1))
                    sizes.append(n)
                except Exception:
                    continue

            if r2_values:
                fig_r2 = go.Figure()
                fig_r2.add_trace(go.Scatter(
                    x=sizes, y=r2_values, mode='lines+markers',
                    line=dict(color='#378ADD', width=2),
                    fill='tozeroy', fillcolor='rgba(55,138,221,0.08)'
                ))
                fig_r2.add_hline(y=50, line_dash="dash", line_color="#D85A30",
                                 annotation_text="50% поріг", annotation_position="bottom right")
                fig_r2.update_layout(
                    height=220, margin=dict(l=0, r=0, t=10, b=0),
                    yaxis=dict(title='%', range=[0, 100]),
                    xaxis=dict(title='Записів'), showlegend=False
                )
                st.plotly_chart(fig_r2, use_container_width=True)
            else:
                st.info("Недостатньо чистих даних для графіку.")
        else:
            st.info("Недостатньо даних для графіку.")

    with col_right:
        st.markdown("##### Вплив факторів на модель")
        if importance is not None:
            fig_imp = go.Figure(go.Bar(
                x=importance['Вплив %'],
                y=importance['Фактор'],
                orientation='h',
                marker_color=['#378ADD','#1D9E75','#BA7517','#888780','#D85A30','#6B4FBB'][:len(importance)],
                text=importance['Вплив %'].astype(str) + '%',
                textposition='outside'
            ))
            fig_imp.update_layout(
                height=220, margin=dict(l=0, r=40, t=10, b=0),
                xaxis=dict(title='%'), showlegend=False
            )
            st.plotly_chart(fig_imp, use_container_width=True)
        else:
            st.info("Дані про важливість факторів очікуються...")

    st.write("---")
    st.markdown("##### Факт vs план ШІ — останні 5 днів (МВт·год/день)")
    if comparison_df is not None:
        fig_cmp = go.Figure()
        fig_cmp.add_trace(go.Scatter(
            x=comparison_df['Дата'], y=comparison_df['Факт (АСЬКЕ)'],
            name='Факт (АСЬКЕ)', mode='lines+markers',
            line=dict(color='#378ADD', width=2)
        ))
        fig_cmp.add_trace(go.Scatter(
            x=comparison_df['Дата'], y=comparison_df['План ШІ'],
            name='План ШІ', mode='lines+markers',
            line=dict(color='#1D9E75', width=2, dash='dash')
        ))
        fig_cmp.add_trace(go.Scatter(
            x=comparison_df['Дата'], y=comparison_df['Прогноз Сайту'],
            name='Прогноз сайту', mode='lines+markers',
            line=dict(color='#D85A30', width=1.5, dash='dot')
        ))
        fig_cmp.update_layout(
            height=220, margin=dict(l=0, r=0, t=10, b=0),
            yaxis=dict(title='МВт·год'),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0)
        )
        st.plotly_chart(fig_cmp, use_container_width=True)
    else:
        st.info("Дані порівняння будуть доступні після накопичення бази.")

    st.write("---")
    st.markdown("##### Похибка прогнозу по годинах доби")
    features = [c for c in ['Forecast_MW','CloudCover','Temp','WindSpeed','PrecipProb'] if c in df_h.columns]

    df_h3 = _clean_numeric(df_h, features + ['Fact_MW'])
    df_clean2 = df_h3[df_h3['Fact_MW'] > 0].dropna(subset=['Fact_MW', 'Time', features[0]]).copy()

    if len(df_clean2) >= 20:
        from sklearn.ensemble import RandomForestRegressor
        df_clean2['hour'] = pd.to_datetime(df_clean2['Time']).dt.hour
        X = df_clean2[features].fillna(0).astype(float)
        y = df_clean2['Fact_MW'].astype(float)
        m = RandomForestRegressor(n_estimators=50, random_state=42)
        m.fit(X, y)
        df_clean2['error'] = abs(m.predict(X) - y)
        hourly_error = df_clean2.groupby('hour')['error'].mean().reset_index()
        hourly_error = hourly_error[(hourly_error['hour'] >= 5) & (hourly_error['hour'] <= 21)]

        fig_err = go.Figure(go.Bar(
            x=hourly_error['hour'],
            y=hourly_error['error'].round(3),
            marker_color='#BA7517'
        ))
        fig_err.update_layout(
            height=180, margin=dict(l=0, r=0, t=10, b=0),
            xaxis=dict(title='Година доби', tickmode='linear', dtick=1),
            yaxis=dict(title='МВт'), showlegend=False
        )
        st.plotly_chart(fig_err, use_container_width=True)
    else:
        st.info("Недостатньо даних для аналізу похибки.")


# ─────────────────────────────────────────────
#  ВКЛАДКА 2: БАЗА
# ─────────────────────────────────────────────

def draw_base_tab(df_h):
    st.markdown("##### 📅 Статистика по днях")

    if df_h.empty:
        st.info("База даних порожня.")
        return

    df = _clean_numeric(df_h.copy(), ['Fact_MW', 'Forecast_MW'])
    df['Time'] = pd.to_datetime(df['Time'])
    df['Дата'] = df['Time'].dt.date

    agg = {}
    if 'Fact_MW' in df.columns:
        agg['Факт (МВт·год)'] = ('Fact_MW', 'sum')
    if 'Forecast_MW' in df.columns:
        agg['Прогноз сайту (МВт·год)'] = ('Forecast_MW', 'sum')

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
    if 'Прогноз сайту (МВт·год)' in daily.columns:
        fig.add_trace(go.Scatter(
            x=daily['Дата'], y=daily['Прогноз сайту (МВт·год)'],
            name='Прогноз сайту', mode='lines+markers',
            line=dict(color='#D85A30', width=2, dash='dash')
        ))
    fig.update_layout(
        height=280, margin=dict(l=0, r=0, t=10, b=0),
        yaxis=dict(title='МВт·год'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        barmode='overlay'
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(
        daily.style.background_gradient(
            subset=['Точність %'] if 'Точність %' in daily.columns else [],
            cmap='RdYlGn', vmin=50, vmax=100
        ),
        use_container_width=True,
        hide_index=True
    )


# ─────────────────────────────────────────────
#  ВКЛАДКА 3: МЕТЕО
# ─────────────────────────────────────────────

def draw_meteo_tab(df_f):
    st.markdown("##### 🌤 Метео-дашборд — прогноз на 5 днів")

    if df_f.empty:
        st.info("Метеодані недоступні.")
        return

    df = df_f.copy()
    df['Time'] = pd.to_datetime(df['Time'])
    cutoff = df['Time'].min() + pd.Timedelta(days=5)
    df = df[df['Time'] <= cutoff]

    row = df.iloc[0] if not df.empty else None
    if row is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🌡 Температура",   f"{row.get('Temp', 0):.1f} °C")
        c2.metric("☁️ Хмарність",     f"{row.get('CloudCover', 0):.0f} %")
        c3.metric("💨 Вітер",         f"{row.get('WindSpeed', 0):.1f} м/с")
        c4.metric("🌧 Опади (імов.)", f"{row.get('PrecipProb', 0):.0f} %")

    st.write("---")

    st.markdown("##### Сонячна радіація та хмарність")
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    fig1.add_trace(go.Scatter(
        x=df['Time'], y=df['Rad'],
        name='Радіація (Вт/м²)', mode='lines',
        line=dict(color='#BA7517', width=2),
        fill='tozeroy', fillcolor='rgba(186,117,23,0.1)'
    ), secondary_y=False)
    if 'CloudCover' in df.columns:
        fig1.add_trace(go.Scatter(
            x=df['Time'], y=df['CloudCover'],
            name='Хмарність (%)', mode='lines',
            line=dict(color='#888780', width=1.5, dash='dot')
        ), secondary_y=True)
    fig1.update_layout(
        height=220, margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='left', x=0),
        hovermode='x unified'
    )
    fig1.update_yaxes(title_text="Вт/м²", secondary_y=False)
    fig1.update_yaxes(title_text="%", secondary_y=True)
    st.plotly_chart(fig1, use_container_width=True)

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
    st.plotly_chart(fig2, use_container_width=True)

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
            st.plotly_chart(fig3, use_container_width=True)
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
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.info("Дані про опади відсутні.")
