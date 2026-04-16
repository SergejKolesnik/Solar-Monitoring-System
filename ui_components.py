import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

def draw_main_chart(df):
    """Головний графік моніторингу"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['Forecast_MW'].head(72), name="Прогноз сайту", line=dict(dash='dot', color='#888888')))
    fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['AI_MW'].head(72), name="План SkyGrid AI", fill='tozeroy', line=dict(color='#00ff7f', width=4)))
    fig.update_layout(template=None, paper_bgcolor='#0e1117', plot_bgcolor='#0e1117', font=dict(color="white"), height=450, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, use_container_width=True, theme=None)

def draw_learning_insights(accuracy, importance_df, error_history, pivot_error, comparison_df):
    """Вкладка НАВЧАННЯ: Тепер з порівнянням за 5 днів та факторами"""
    st.subheader(f"🧠 Аналітика навчання (Точність: {accuracy:.1f}%)")
    
    # 1. ПОРІВНЯЛЬНИЙ ГРАФІК (Факт vs Сайт vs ШІ)
    st.write("📊 **Порівняння генерації за останні 5 днів (МВт·год)**")
    if comparison_df is not None:
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(x=comparison_df['Дата'], y=comparison_df['Факт (АСКОЕ)'], name='Факт (АСКОЕ)', marker_color='#00ff7f'))
        fig_comp.add_trace(go.Bar(x=comparison_df['Дата'], y=comparison_df['Прогноз Сайту'], name='Прогноз Сайту', marker_color='#888888'))
        fig_comp.add_trace(go.Bar(x=comparison_df['Дата'], y=comparison_df['План ШІ'], name='План ШІ', marker_color='#00d4ff'))
        
        fig_comp.update_layout(template=None, barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                               font=dict(color="white"), height=400, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig_comp, use_container_width=True, theme=None)

    c1, c2 = st.columns(2)
    with c1:
        st.write("📈 **Вплив факторів (Вага коефіцієнтів)**")
        # Горизонтальні стовпчики для кожного фактора
        fig_imp = px.bar(importance_df, x='Коефіцієнт', y='Фактор', orientation='h', color='Коефіцієнт', color_continuous_scale='Greens')
        fig_imp.update_layout(template=None, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="white"), height=300, showlegend=False)
        st.plotly_chart(fig_imp, use_container_width=True, theme=None)

    with c2:
        st.write("📉 **Динаміка похибки (Дельта)**")
        fig_err = go.Figure(go.Scatter(x=error_history['Time'], y=error_history['Error'], fill='tozeroy', line=dict(color='#FFA500')))
        fig_err.update_layout(template=None, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="white"), height=300)
        st.plotly_chart(fig_err, use_container_width=True, theme=None)

    st.write("🔥 **Теплова карта системних помилок**")
    fig_heat = px.imshow(pivot_error, color_continuous_scale='RdBu_r', aspect="auto")
    fig_heat.update_layout(template=None, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font=dict(color="white"),
                          coloraxis_colorbar=dict(bgcolor='rgba(0,0,0,0)', tickfont=dict(color="white"), outlinecolor='rgba(0,0,0,0)'))
    st.plotly_chart(fig_heat, use_container_width=True, theme=None)

def draw_metrics(df, now_ua, timedelta):
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        d = (now_ua + timedelta(days=i)).date()
        val = df[df['Time'].dt.date == d]['AI_MW'].sum()
        col.metric(f"{d.strftime('%d.%m')}", f"{val:.2f} МВт·год")
