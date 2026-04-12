import streamlit as st
import plotly.graph_objects as go

def draw_main_chart(df):
    fig = go.Figure()
    
    # Автоматичний пошук колонки сайту (шукаємо всі можливі варіанти)
    site_candidates = ['Прогноз сайту (МВт)', 'Forecast_MW', 'Прогноз сайту']
    site_col = next((c for c in site_candidates if c in df.columns), None)
    
    # Автоматичний пошук колонки ШІ
    ai_candidates = ['Прогноз ШІ (МВт)', 'AI_MW', 'Прогноз ШІ']
    ai_col = next((c for c in ai_candidates if c in df.columns), None)

    # 1. МАЛЮЄМО САЙТ (Сірий пунктир)
    if site_col:
        fig.add_trace(go.Scatter(
            x=df['Time'].head(72), 
            y=df[site_col].head(72), 
            name="Прогноз сайту", 
            line=dict(dash='dot', color='gray', width=2)
        ))
        
    # 2. МАЛЮЄМО ШІ (Зелена область)
    if ai_col:
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
