import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # 1. Нормалізація
    df_h = df_h.copy()
    df_h['Time'] = pd.to_datetime(df_h['Time'], errors='coerce')
    df_h = df_h.dropna(subset=['Time'])
    
    # Спільні фактори (регістронезалежно)
    df_h.columns = df_h.columns.str.strip()
    df_f.columns = df_f.columns.str.strip()
    target_features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    existing_features = [c for c in target_features if c in df_h.columns and c in df_f.columns]
    
    # Дані для навчання (мінімум 20 рядків з Фактом)
    df_train = df_h.dropna(subset=['Fact_MW'] + existing_features)
    if len(df_train) < 20:
        return df_f['Forecast_MW'], 0.0, None, None, None, None

    # 2. Навчання
    X = df_train[existing_features].fillna(0)
    y = df_train['Fact_MW'].astype(float)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 3. Прогноз та аналітика
    predictions = model.predict(df_f[existing_features].fillna(0))
    accuracy = model.score(X, y) * 100

    # Важливість факторів (коефіцієнти)
    importance = pd.DataFrame({
        'Фактор': existing_features, 
        'Коефіцієнт': model.feature_importances_
    }).sort_values(by='Коефіцієнт', ascending=False)

    # 4. Порівняльний аналіз за останні 5 днів (Історія)
    hist_5d = df_train.tail(24 * 5).copy()
    hist_5d['AI_Plan'] = model.predict(hist_5d[existing_features].fillna(0))
    
    # Групуємо по днях
    comparison_df = hist_5d.groupby(hist_5d['Time'].dt.date).agg({
        'Fact_MW': 'sum',
        'Forecast_MW': 'sum',
        'AI_Plan': 'sum'
    }).reset_index()
    comparison_df.columns = ['Дата', 'Факт (АСКОЕ)', 'Прогноз Сайту', 'План ШІ']

    # Історія помилок для теплової карти
    error_history = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(24 * 7).copy()
    error_history['Error'] = error_history['Fact_MW'] - error_history['Forecast_MW']
    heatmap_df = error_history.copy()
    heatmap_df['Hour'] = heatmap_df['Time'].dt.hour
    heatmap_df['Date'] = heatmap_df['Time'].dt.strftime('%d.%m')
    pivot_error = heatmap_df.pivot_table(index='Hour', columns='Date', values='Error', aggfunc='mean').fillna(0)
    
    return predictions, accuracy, importance, error_history, pivot_error, comparison_df
