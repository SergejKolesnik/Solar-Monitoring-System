import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    df_h = df_h.copy()
    df_h['Time'] = pd.to_datetime(df_h['Time'], errors='coerce')
    df_h = df_h.dropna(subset=['Time'])
    
    # Вибір факторів (приведення до одного регістру)
    all_features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    df_h.columns = df_h.columns.str.strip()
    df_f.columns = df_f.columns.str.strip()
    existing_features = [c for c in all_features if c in df_h.columns and c in df_f.columns]
    
    # Фільтрація: беремо останні 7 днів для аналізу помилок
    df_train = df_h.dropna(subset=['Fact_MW'] + [existing_features[0]])
    if len(df_train) < 10:
        return df_f['Forecast_MW'], 0.0, None, None, None

    # Навчання
    X = df_train[existing_features].fillna(0)
    y = df_train['Fact_MW'].astype(float)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # Прогноз
    predictions = model.predict(df_f[existing_features].fillna(0))
    accuracy = model.score(X, y) * 100

    # 1. Важливість факторів
    importance = pd.DataFrame({'Фактор': existing_features, 'Важливість': model.feature_importances_}).sort_values(by='Важливість', ascending=False)

    # 2. Дані для графіка помилок (7 днів)
    error_history = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(24 * 7).copy()
    error_history['Error'] = error_history['Fact_MW'] - error_history['Forecast_MW']

    # 3. Дані для ТЕПЛОВОЇ КАРТИ (Помилка: Година vs День)
    heatmap_data = error_history.copy()
    heatmap_data['Hour'] = heatmap_data['Time'].dt.hour
    heatmap_data['Date'] = heatmap_data['Time'].dt.strftime('%d.%m')
    # Створюємо матрицю помилок
    pivot_error = heatmap_data.pivot_table(index='Hour', columns='Date', values='Error', aggfunc='mean').fillna(0)
    
    return predictions, accuracy, importance, error_history, pivot_error
