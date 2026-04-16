import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

def draw_main_chart(df):
    """Оновлений професійний графік генерації"""
    fig = go.Figure()

    # 1. Прогноз сайту (сірий пунктир)
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), 
        y=df['Forecast_MW'].head(72), 
        name="Прогноз сайту", 
        line=dict(dash='dot', color='rgba(180, 180, 180, 0.6)', width=2)
    ))

    # 2. План ШІ (Зелена область із градієнтом)
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), 
        y=df['AI_MW'].head(72), 
        name="План SkyGrid AI", 
        fill='tozeroy', 
        fillcolor='rgba(0, 255, 127, 0.2)', # М'яке зелене заповнення
        line=dict(color='#00ff7f', width=4) # Товста яскрава лінія
    ))

    # 3. Налаштування зовнішнього вигляду
    fig.update_layout(
        hovermode="x unified",
        # Темна тема для самого графіка
        paper_bgcolor='rgba(15, 15, 15, 1)', 
        plot_bgcolor='rgba(15, 15, 15, 1)',
        font=dict(color="white"),
        margin=dict(l=10, r=10, t=50, b=10),
        height=500,
        legend=dict(
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="right", 
            x=1,
            font=dict(size=12)
        ),
        xaxis=dict(
            showgrid=True, 
            gridcolor='rgba(255, 255, 255, 0.1)', # Ледь помітна сітка
            title="Час (години)"
        ),
        yaxis=dict(
            showgrid=True, 
            gridcolor='rgba(255, 255, 255, 0.1)', 
            title="Потужність, МВт",
            zerolinecolor='rgba(255, 255, 255, 0.3)'
        )
    )

    st.plotly_chart(fig, use_container_width=True)

def draw_learning_insights(accuracy, importance_df, error_history, pivot_error):
    """Графіки для вкладки НАВЧАННЯ - тепер теж у темному стилі"""
    st.subheader(f"🧠 Аналітика ШІ (Точність: {accuracy:.1f}%)")
    
    c1, c2 = st.columns(2)
    with c1:
        st.write("📊 **Важливість факторів**")
        fig_imp = px.bar(importance_df, x='Важливість', y='Фактор', orientation='h', color='Важливість', color_continuous_scale='Greens')
        fig_imp.update_layout(
            template='plotly_dark', 
            height=300, 
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_imp, use_container_width=True)

    with c2:
        st.write("📉 **Динаміка похибки (Дельта)**")
        fig_err = go.Figure(go.Scatter(
            x=error_history['Time'], 
            y=error_history['Error'], 
            fill='tozeroy', 
            line=dict(color='#FFA500'), # Помаранчева лінія для помилок
            fillcolor='rgba(255, 165, 0, 0.1)'
        ))
        fig_err.update_layout(
            template='plotly_dark', 
            height=300, 
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        st.plotly_chart(fig_err, use_container_width=True)

    st.write("🔥 **Теплова карта системних помилок**")
    fig_heat = px.imshow(pivot_error, 
                         labels=dict(x="Дата", y="Година", color="Δ МВт"),
                         x=pivot_error.columns, y=pivot_error.index,
                         color_continuous_scale='RdBu_r', 
                         aspect="auto")
    fig_heat.update_layout(template='plotly_dark', height=400)
    st.plotly_chart(fig_heat, use_container_width=True)

def draw_metrics(df, now_ua, timedelta):
    """Метрики з кольоровими індикаторами"""
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d = (now_ua + timedelta(days=i)).date()
        daily_sum = df[df['Time'].dt.date == d]['AI_MW'].sum()
        col.metric(f"📅 {d.strftime('%d.%m')}", f"{daily_sum:.2f} МВт·год")
