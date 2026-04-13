import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # Фактори для навчання
    features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # Перевіряємо наявність колонок у базі
    missing_cols = [c for c in features if c not in df_h.columns]
    
    # Якщо колонок немає або мало даних, повертаємо базовий прогноз
    df_train = df_h.dropna(subset=['Fact_MW', 'Forecast_MW'])
    if missing_cols or len(df_train) < 50:
        return df_f['Forecast_MW'], 0.0, None, None

    # Навчання на розширених даних
    df_train = df_h.dropna(subset=features + ['Fact_MW'])
    X = df_train[features]
    y = df_train['Fact_MW']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # Прогноз та аналітика
    predictions = model.predict(df_f[features])
    accuracy = model.score(X, y) * 100

    # Важливість факторів (що найбільше впливає на результат)
    importance = pd.DataFrame({
        'Фактор': ['Сайт', 'Хмари', 'Темп.', 'Вітер', 'Опади'],
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    # Дані для графіка дельти
    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(50).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
