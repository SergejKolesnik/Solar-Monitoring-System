import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # Повний список бажаних факторів
    features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # Вибираємо тільки ті, що реально є в CSV
    existing_features = [c for c in features if c in df_h.columns]
    
    # Якщо бази немає або вона порожня - не ламаємо програму
    if 'Forecast_MW' not in existing_features or len(df_h.dropna(subset=['Fact_MW'])) < 10:
        return df_f['Forecast_MW'], 0.0, None, None

    # Навчання на тому, що маємо
    df_train = df_h.dropna(subset=existing_features + ['Fact_MW'])
    X = df_train[existing_features]
    y = df_train['Fact_MW']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # Прогноз
    predictions = model.predict(df_f[existing_features])
    accuracy = model.score(X, y) * 100

    # Аналітика
    importance = pd.DataFrame({'Фактор': existing_features, 'Важливість': model.feature_importances_})
    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(50).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
