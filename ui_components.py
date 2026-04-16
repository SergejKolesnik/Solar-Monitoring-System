import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

def draw_main_chart(df):
    """Фінальна версія: повністю темний професійний графік"""
    fig = go.Figure()

    # 1. Прогноз сайту (сірий пунктир)
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), 
        y=df['Forecast_MW'].head(72), 
        name="Прогноз сайту", 
        line=dict(dash='dot', color='rgba(200, 200, 200, 0.5)', width=2)
    ))

    # 2. План SkyGrid AI (Зелена лінія з підсвіткою)
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), 
        y=df['AI_MW'].head(72), 
        name="План SkyGrid AI", 
        fill='tozeroy', 
        fillcolor='rgba(0, 255, 127, 0.15)', # Легке зелене сяйво
        line=dict(color='#00ff7f', width=4)
    ))

    # 3. ПОВНЕ ВИДАЛЕННЯ БІЛОГО ФОНУ
    fig.update_layout(
        hovermode="x unified",
        paper_bgcolor='#0e1117', # Темний фон сторінки Streamlit
        plot_bgcolor='#1a1c23',  # Темний фон самої області графіка
        font=dict(color="#e0e0e0"),
        margin=dict(l=10, r=10, t=50, b=10),
        height=500,
        legend=dict(
            orientation="h", 
            yanchor="bottom", y=1.02, 
            xanchor="right", x=1,
            font=dict(size=12)
        ),
        xaxis=dict(
            showgrid=True, 
            gridcolor='rgba(255, 255, 255, 0.05)', # Дуже м'яка сітка
            linecolor='rgba(255, 255, 255, 0.2)',
            title="Час (72 години)"
        ),
        yaxis=dict(
            showgrid=True, 
            gridcolor='rgba(255, 255, 255, 0.05)',
            linecolor='rgba(255, 255, 255, 0.2)',
            title="Потужність, МВт"
        )
    )

    st.plotly_chart(fig, use_container_width=True)

def draw_learning_insights(accuracy, importance_df, error_history, pivot_error):
    """Аналітика теж у глибокому темному стилі"""
    st.subheader(f"🧠 Аналітика ШІ (Точність: {accuracy:.1f}%)")
    
    # Використовуємо темний шаблон Plotly за замовчуванням
    c1, c2 = st.columns(2)
    with c1:
        st.write("📊 **Важливість факторів**")
        fig = px.bar(importance_df, x='Важливість', y='Фактор', orientation='h', color_discrete_sequence=['#00ff7f'])
        fig.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.write("📉 **Динаміка похибки (7 днів)**")
        fig_err = go.Figure(go.Scatter(x=error_history['Time'], y=error_history['Error'], fill='tozeroy', line=dict(color='#FFA500'), fillcolor='rgba(255, 165, 0, 0.1)'))
        fig_err.update_layout(template='plotly_dark', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=300)
        st.plotly_chart(fig_err, use_container_width=True)

    st.write("🔥 **Теплова карта помилок (Година / День)**")
    fig_heat = px.imshow(pivot_error, color_continuous_scale='RdBu_r', aspect="auto")
    fig_heat.update_layout(template='plotly_dark', height=400)
    st.plotly_chart(fig_heat, use_container_width=True)

def draw_metrics(df, now_ua, timedelta):
    """Картки генерації"""
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d = (now_ua + timedelta(days=i)).date()
        val = df[df['Time'].dt.date == d]['AI_MW'].sum()
        col.metric(f"{d.strftime('%d.%m')}", f"{val:.2f} МВт·год")
