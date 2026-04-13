import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

def draw_main_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['Forecast_MW'].head(72), name="Прогноз сайту", line=dict(dash='dot', color='gray')))
    fig.add_trace(go.Scatter(x=df['Time'].head(72), y=df['AI_MW'].head(72), name="План ШІ", fill='tozeroy', line=dict(color='#00ff7f')))
    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", y=1.05), margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)

def draw_learning_insights(accuracy, importance_df, error_df):
    st.subheader(f"🧠 Стан навчання (Точність: {accuracy:.1f}%)")
    c1, c2 = st.columns(2)
    with c1:
        st.write("📊 **Вплив факторів на рішення ШІ:**")
        fig_imp = px.bar(importance_df, x='Важливість', y='Фактор', orientation='h', color='Важливість', color_continuous_scale='Greens')
        fig_imp.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig_imp, use_container_width=True)
    with c2:
        st.write("📉 **Історія дельти (Факт - Сайт):**")
        fig_err = go.Figure()
        fig_err.add_trace(go.Scatter(x=error_df['Time'], y=error_df['Error'], fill='tozeroy', line=dict(color='orange')))
        fig_err.update_layout(height=300)
        st.plotly_chart(fig_err, use_container_width=True)

def draw_metrics(df, now_ua, timedelta):
    c1, c2, c3 = st.columns(3)
    for i, col in enumerate([c1, c2, c3]):
        t_date = (now_ua + timedelta(days=i)).date()
        d_slice = df[df['Time'].dt.date == t_date]
        if not d_slice.empty:
            col.metric(f"{t_date.strftime('%d.%m')}", f"{d_slice['AI_MW'].sum():.2f} МВт·год")
