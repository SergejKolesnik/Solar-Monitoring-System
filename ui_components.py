import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

def draw_training_tab(df_h, accuracy_r2, mse_error, importance, scatter_data, comparison_df):

    # --- 4 метрики вгорі ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("R² (тест)", f"{accuracy_r2:.1f}%")
    c2.metric("MSE похибка", f"{mse_error:.4f}")
    c3.metric("Записів у базі", f"{len(df_h):,}")
    c4.metric("Активних факторів", len(importance) if importance is not None else 0)

    st.write("---")
    col_left, col_right = st.columns(2)

    # --- R² vs кількість даних ---
    with col_left:
        st.markdown("##### Як R² росте з кількістю даних")
        if len(df_h) >= 20:
            steps = list(range(20, len(df_h), max(1, len(df_h) // 15))) + [len(df_h)]
            from sklearn.ensemble import RandomForestRegressor
            from sklearn.metrics import r2_score
            from sklearn.model_selection import train_test_split

            features = [c for c in ['Forecast_MW','CloudCover','Temp','WindSpeed','PrecipProb'] if c in df_h.columns]
            df_clean = df_h.dropna(subset=['Fact_MW', features[0]])

            r2_values, sizes = [], []
            for n in steps:
                subset = df_clean.iloc[:n]
                if len(subset) < 20:
                    continue
                X = subset[features].fillna(0)
                y = subset['Fact_MW'].astype(float)
                try:
                    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
                    m = RandomForestRegressor(n_estimators=30, random_state=42)
                    m.fit(X_tr, y_tr)
                    r2_values.append(round(r2_score(y_te, m.predict(X_te)) * 100, 1))
                    sizes.append(n)
                except Exception:
                    continue

            fig_r2 = go.Figure()
            fig_r2.add_trace(go.Scatter(
                x=sizes, y=r2_values, mode='lines+markers',
                line=dict(color='#378ADD', width=2),
                fill='tozeroy', fillcolor='rgba(55,138,221,0.08)',
                name='R²'
            ))
            fig_r2.add_hline(y=50, line_dash="dash", line_color="#D85A30",
                             annotation_text="50% поріг", annotation_position="bottom right")
            fig_r2.update_layout(
                height=220, margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(title='%', range=[0, 100]),
                xaxis=dict(title='Записів'),
                showlegend=False
            )
            st.plotly_chart(fig_r2, use_container_width=True)
        else:
            st.info("Недостатньо даних для графіку.")

    # --- Важливість факторів ---
    with col_right:
        st.markdown("##### Вплив факторів на модель")
        if importance is not None:
            fig_imp = go.Figure(go.Bar(
                x=importance['Вплив %'],
                y=importance['Фактор'],
                orientation='h',
                marker_color=['#378ADD','#1D9E75','#BA7517','#888780','#D85A30'][:len(importance)],
                text=importance['Вплив %'].astype(str) + '%',
                textposition='outside'
            ))
            fig_imp.update_layout(
                height=220, margin=dict(l=0, r=40, t=10, b=0),
                xaxis=dict(title='%'),
                showlegend=False
            )
            st.plotly_chart(fig_imp, use_container_width=True)
        else:
            st.info("Дані про важливість факторів очікуються...")

    st.write("---")

    # --- Факт vs план ШІ по днях ---
    st.markdown("##### Факт vs план ШІ — останні 7 днів (МВт·год/день)")
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

    # --- Похибка по годинах доби ---
    st.markdown("##### Похибка прогнозу по годинах доби")
    if scatter_data is not None:
        df_h_copy = df_h.copy()
        features = [c for c in ['Forecast_MW','CloudCover','Temp','WindSpeed','PrecipProb'] if c in df_h_copy.columns]
        df_clean = df_h_copy.dropna(subset=['Fact_MW', 'Time'] + [features[0]])
        df_clean['hour'] = pd.to_datetime(df_clean['Time']).dt.hour

        from sklearn.ensemble import RandomForestRegressor
        X = df_clean[features].fillna(0)
        y = df_clean['Fact_MW'].astype(float)
        if len(df_clean) >= 20:
            m = RandomForestRegressor(n_estimators=50, random_state=42)
            m.fit(X, y)
            df_clean['error'] = abs(m.predict(X) - y)
            hourly_error = df_clean.groupby('hour')['error'].mean().reset_index()
            hourly_error = hourly_error[(hourly_error['hour'] >= 5) & (hourly_error['hour'] <= 21)]

            fig_err = go.Figure(go.Bar(
                x=hourly_error['hour'],
                y=hourly_error['error'].round(3),
                marker_color='#BA7517',
                name='Похибка (МВт)'
            ))
            fig_err.update_layout(
                height=180, margin=dict(l=0, r=0, t=10, b=0),
                xaxis=dict(title='Година доби', tickmode='linear', dtick=1),
                yaxis=dict(title='МВт'),
                showlegend=False
            )
            st.plotly_chart(fig_err, use_container_width=True)
        else:
            st.info("Недостатньо даних для аналізу похибки.")
    else:
        st.info("Графік похибки буде доступний після оновлення моделі.")
