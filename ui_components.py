import streamlit as st
import plotly.graph_objects as go
import pandas as pd

def draw_main_chart(df):
    fig = go.Figure()
    # Прогноз сайту (пунктир)
    if 'Forecast_MW' in df.columns:
        fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['Forecast_MW'].head(72), 
                                 name="Прогноз сайту", line=dict(dash='dot', color='gray')))
    # План ШІ (заповнена область)
    if 'AI_MW' in df.columns:
        fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['AI_MW'].head(72), 
                                 name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    
    fig.update_layout(hovermode="x unified", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

def draw_training_stats(df_history, accuracy):
    st.subheader(f"Результати навчання: {accuracy:.1f}%")
    if not df_history.empty:
        st.write("Останні дані АСКОЕ, використані для навчання:")
        st.dataframe(df_history.tail(10), use_container_width=True)
    else:
        st.warning("Недостатньо даних у базі для аналізу.")
