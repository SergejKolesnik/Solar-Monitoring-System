import streamlit as st
import plotly.graph_objects as go

def draw_main_chart(df):
    fig = go.Figure()
    
    # Визначаємо колонки (захист від перейменувань)
    s_col = 'Прогноз сайту (МВт)' if 'Прогноз сайту (МВт)' in df.columns else 'Forecast_MW'
    a_col = 'Прогноз ШІ (МВт)' if 'Прогноз ШІ (МВт)' in df.columns else 'AI_MW'

    # 1. Прогноз сайту (сірий пунктир)
    if s_col in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Time'].head(72), y=df[s_col].head(72),
            name="Прогноз сайту",
            line=dict(dash='dot', color='gray', width=2)
        ))
        
    # 2. План ШІ (зелена область)
    if a_col in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Time'].head(72), y=df[a_col].head(72),
            name="План ШІ",
            fill='tozeroy',
            line=dict(color='#00ff7f', width=3)
        ))
    
    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=0, r=0, t=30, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)

def draw_training_stats(df_h, acc):
    st.metric("Точність моделі", f"{acc:.1f}%")
    st.write(f"База: {len(df_h)} записів")
