import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

def draw_main_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['Forecast_MW'].head(72), name="Прогноз сайту", line=dict(dash='dot', color='gray')))
    fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['AI_MW'].head(72), name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f')))
    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.1), margin=dict(l=0, r=0, t=40, b=0), height=450, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)

def draw_learning_insights(accuracy, importance_df, error_history, pivot_error):
    st.subheader(f"🧠 Аналітика ШІ (Точність: {accuracy:.1f}%)")
    
    # --- БЛОК 1: ВАЖЛИВІСТЬ ТА ПОМИЛКА ---
    c1, c2 = st.columns(2)
    with c1:
        st.write("📊 **Що найбільше впливає на прогноз?**")
        st.info("Цей графік показує, які метеодані ШІ вважає ключовими. Чим довша лінія, тим сильніше параметр (напр. Хмарність) змінює виробіток.")
        fig_imp = px.bar(importance_df, x='Важливість', y='Фактор', orientation='h', color='Важливість', color_continuous_scale='Greens')
        fig_imp.update_layout(height=300, showlegend=False, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_imp, use_container_width=True)

    with c2:
        st.write("📉 **Динаміка помилки (Дельта) за 7 днів**")
        st.info("Показує різницю між фактом і сайтом. Якщо лінія вище нуля — сайт недооцінив сонце, якщо нижче — переоцінив.")
        fig_err = go.Figure(go.Scatter(x=error_history['Time'], y=error_history['Error'], fill='tozeroy', line=dict(color='orange'), fillcolor='rgba(255,165,0,0.2)'))
        fig_err.update_layout(height=300, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig_err, use_container_width=True)

    # --- БЛОК 2: ТЕПЛОВА КАРТА ---
    st.write("🔥 **Теплова карта помилок (Година / День)**")
    st.info("Червоні зони — сайт сильно помилився в плюс, сині — в мінус. Допомагає побачити системні помилки в конкретні години.")
    fig_heat = px.imshow(pivot_error, 
                         labels=dict(x="Дата", y="Година", color="Помилка (МВт)"),
                         x=pivot_error.columns, y=pivot_error.index,
                         color_continuous_scale='RdBu_r', aspect="auto")
    fig_heat.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig_heat, use_container_width=True)

def draw_metrics(df, now_ua, timedelta):
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d = (now_ua + timedelta(days=i)).date()
        val = df[df['Time'].dt.date == d]['AI_MW'].sum()
        col.metric(f"{d.strftime('%d.%m')}", f"{val:.2f} МВт·год")
