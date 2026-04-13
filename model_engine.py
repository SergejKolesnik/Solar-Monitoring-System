import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # Повний набір колонок, які ми ХОЧЕМО бачити
    desired_features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # 1. Вибираємо ТІЛЬКИ ті колонки, які РЕАЛЬНО є у файлі
    existing_features = [c for c in desired_features if c in df_h.columns]
    
    # Якщо немає навіть базових даних для навчання — виходимо
    if 'Forecast_MW' not in existing_features or len(df_h.dropna(subset=['Fact_MW'])) < 10:
        return df_f['Forecast_MW'], 0.0, None, None

    # 2. Навчання на наявному максимумі даних
    df_train = df_h.dropna(subset=existing_features + ['Fact_MW'])
    X = df_train[existing_features].fillna(0)
    y = df_train['Fact_MW']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 3. Прогноз
    X_future = df_f[existing_features].fillna(0)
    predictions = model.predict(X_future)
    accuracy = model.score(X, y) * 100

    # 4. Важливість факторів (для візуалізації навчання)
    importance = pd.DataFrame({
        'Фактор': existing_features,
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    # Дані для дельти
    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(50).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
