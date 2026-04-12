import streamlit as st
import plotly.graph_objects as go

def draw_main_chart(df):
    fig = go.Figure()
    # Сірий пунктир - Сайт
    fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['Forecast_MW'].head(72), 
                             name="Прогноз сайту", line=dict(dash='dot', color='gray')))
    # Зелена область - ШІ
    fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['AI_MW'].head(72), 
                             name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f', width=3)))
    
    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)

def draw_training_stats(df_history, accuracy):
    st.subheader(f"🧠 Точність ШІ: {accuracy:.1f}%")
    st.write(f"База навчання: {len(df_history)} записів АСКОЕ.")
