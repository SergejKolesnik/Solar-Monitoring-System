import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

def draw_main_chart(df):
    """Версія з повним ігноруванням тем Streamlit"""
    fig = go.Figure()

    # 1. Прогноз сайту
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), 
        y=df['Forecast_MW'].head(72), 
        name="Прогноз сайту", 
        line=dict(dash='dot', color='#888888', width=2)
    ))

    # 2. План SkyGrid AI
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), 
        y=df['AI_MW'].head(72), 
        name="План SkyGrid AI", 
        fill='tozeroy', 
        fillcolor='rgba(0, 255, 127, 0.1)', 
        line=dict(color='#00ff7f', width=4)
    ))

    # 3. ТОТАЛЬНИЙ КОНТРОЛЬ КОЛЬОРУ
    fig.update_layout(
        template=None, # Вимикаємо стандартні шаблони
        hovermode="x unified",
        paper_bgcolor='#0e1117', # Фон паперу
        plot_bgcolor='#0e1117',  # Фон області малювання (ТЕПЕР ТОЧНО ТЕМНИЙ)
        font=dict(color="#e0e0e0"),
        margin=dict(l=10, r=10, t=50, b=10),
        height=500,
        legend=dict(orientation="h", y=1.05, x=1, xanchor="right"),
        xaxis=dict(
            showgrid=True, 
            gridcolor='#262730', # Темна сітка
            zeroline=False,
            title="Години"
        ),
        yaxis=dict(
            showgrid=True, 
            gridcolor='#262730',
            zeroline=False,
            title="МВт"
        )
    )

    # Вимикаємо вбудовану тему Streamlit для цього графіка
    st.plotly_chart(fig, use_container_width=True, theme=None)

def draw_learning_insights(accuracy, importance_df, error_history, pivot_error):
    """Аналітика без білих плям"""
    st.subheader(f"🧠 Аналітика ШІ (Точність: {accuracy:.1f}%)")
    
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(importance_df, x='Важливість', y='Фактор', orientation='h')
        fig.update_traces(marker_color='#00ff7f')
        fig.update_layout(template=None, paper_bgcolor='#0e1117', plot_bgcolor='#0e1117', 
                          font=dict(color="white"), height=300, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig, use_container_width=True, theme=None)

    with c2:
        fig_err = go.Figure(go.Scatter(x=error_history['Time'], y=error_history['Error'], fill='tozeroy', line=dict(color='#FFA500')))
        fig_err.update_layout(template=None, paper_bgcolor='#0e1117', plot_bgcolor='#0e1117', 
                              font=dict(color="white"), height=300, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig_err, use_container_width=True, theme=None)

    st.write("🔥 Теплова карта помилок")
    fig_heat = px.imshow(pivot_error, color_continuous_scale='RdBu_r', aspect="auto")
    fig_heat.update_layout(template=None, paper_bgcolor='#0e1117', plot_bgcolor='#0e1117', font=dict(color="white"))
    st.plotly_chart(fig_heat, use_container_width=True, theme=None)

def draw_metrics(df, now_ua, timedelta):
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d = (now_ua + timedelta(days=i)).date()
        val = df[df['Time'].dt.date == d]['AI_MW'].sum()
        col.metric(f"{d.strftime('%d.%m')}", f"{val:.2f} МВт·год")
