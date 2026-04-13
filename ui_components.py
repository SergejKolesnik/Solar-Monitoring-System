import streamlit as st
import plotly.graph_objects as go

def draw_main_chart(df):
    fig = go.Figure()
    # Сірий пунктир (Сайт)
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), y=df['Forecast_MW'].head(72),
        name="Прогноз сайту",
        line=dict(dash='dot', color='rgba(150, 150, 150, 0.8)', width=2)
    ))
    # Зелена область (ШІ)
    fig.add_trace(go.Scatter(
        x=df['Time'].head(72), y=df['AI_MW'].head(72),
        name="План ШІ (коригований)",
        fill='tozeroy',
        fillcolor='rgba(0, 255, 127, 0.3)',
        line=dict(color='#00ff7f', width=3)
    ))
    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        margin=dict(l=0, r=0, t=40, b=0), height=500,
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.1)')
    )
    st.plotly_chart(fig, use_container_width=True)

def draw_metrics(df, now_ua, timedelta):
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        target_date = (now_ua + timedelta(days=i)).date()
        d_slice = df[df['Time'].dt.date == target_date]
        if not d_slice.empty:
            col.metric(f"{target_date.strftime('%d.%m')}", f"{d_slice['AI_MW'].sum():.2f} МВт·год")
