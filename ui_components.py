import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# --- 1. ФУНКЦІЯ ДЛЯ ГОЛОВНОЇ СТОРІНКИ (МОНІТОРИНГ) ---
def draw_main_chart(df):
    """Малює основний графік: Прогноз сайту vs План ШІ."""
    fig = go.Figure()

    # Сірий пунктир (Сайт)
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), 
        y=df['Forecast_MW'].head(72), 
        name="Прогноз сайту", 
        line=dict(dash='dot', color='rgba(150, 150, 150, 0.8)', width=2)
    ))

    # Зелена область (ШІ)
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), 
        y=df['AI_MW'].head(72), 
        name="План ШІ (коригований)", 
        fill='tozeroy', 
        fillcolor='rgba(0, 255, 127, 0.3)', 
        line=dict(color='#00ff7f', width=3)
    ))

    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        margin=dict(l=0, r=0, t=40, b=0),
        height=500,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
    )
    st.plotly_chart(fig, use_container_width=True)

def draw_metrics(df, now_ua, timedelta):
    """Відображає сумарні метрики на 3 дні."""
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        target_date = (now_ua + timedelta(days=i)).date()
        d_slice = df[df['Time'].dt.date == target_date]
        if not d_slice.empty:
            val = d_slice['AI_MW'].sum()
            col.metric(f"{target_date.strftime('%d.%m')}", f"{val:.2f} МВт·год")

# --- 2. НОВІ ФУНКЦІЇ ДЛЯ ВКЛАДКИ "НАВЧАННЯ" (АНАЛІТИКА) ---
def draw_learning_insights(accuracy, importance_df, error_df):
    """Візуалізує 'роботу мозку': важливість факторів та помилки."""
    st.subheader(f"🧠 Стан ШІ-моделі (Точність: {accuracy:.1f}%)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("📊 **На що звертає увагу мозок:**")
        # Графік важливості факторів (горизонтальний Bar Chart)
        fig_imp = px.bar(importance_df, x='Важливість', y='Фактор', orientation='h',
                         color='Вачивність', color_continuous_scale='Greens')
        fig_imp.update_layout(
            height=300, 
            showlegend=False, 
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="white")
        )
        st.plotly_chart(fig_imp, use_container_width=True)

    with col2:
        st.write("📉 **Динаміка помилки сайту (Дельта):**")
        # Графік розбіжності (Факт - Прогноз сайту)
        fig_err = go.Figure()
        fig_err.add_trace(go.Scatter(
            x=error_df['Time'], 
            y=error_df['Error'], 
            fill='tozeroy', 
            name='Помилка сайту',
            line=dict(color='orange', width=1),
            fillcolor='rgba(255, 165, 0, 0.2)'
        ))
        fig_err.update_layout(
            height=300, 
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color="white")
        )
        st.plotly_chart(fig_err, use_container_width=True)
