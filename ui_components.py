import streamlit as st
import plotly.graph_objects as go

def draw_main_chart(df):
    fig = go.Figure()
    
    # Визначаємо, яка колонка відповідає за прогноз сайту
    site_col = 'Прогноз сайту (МВт)' if 'Прогноз сайту (МВт)' in df.columns else 'Forecast_MW'
    # Визначаємо, яка колонка відповідає за прогноз ШІ
    ai_col = 'Прогноз ШІ (МВт)' if 'Прогноз ШІ (МВт)' in df.columns else 'AI_MW'

    # 1. Сірий пунктир (Прогноз сайту)
    if site_col in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Time'].head(72), 
            y=df[site_col].head(72), 
            name="Прогноз сайту", 
            line=dict(dash='dot', color='gray', width=2)
        ))
        
    # 2. Зелена область (Прогноз ШІ)
    if ai_col in df.columns:
        fig.add_trace(go.Scatter(
            x=df['Time'].head(72), 
            y=df[ai_col].head(72), 
            name="Прогноз ШІ (коригований)", 
            fill='tozeroy', 
            line=dict(color='#00ff7f', width=3)
        ))
    
    fig.update_layout(
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=0, r=0, t=30, b=0)
    )
    st.plotly_chart(fig, use_container_width=True)

def draw_training_stats(df_history, accuracy):
    st.subheader(f"🧠 Діагностика ШІ")
    c1, c2 = st.columns(2)
    c1.metric("Точність моделі", f"{accuracy:.1f}%")
    c2.metric("Даних у базі", f"{len(df_history)} год.")
