import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # Повний список бажаних факторів
    all_features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # 1. Вибираємо тільки ті колонки, які реально існують у вашому CSV
    existing_features = [c for c in all_features if c in df_h.columns]
    
    # 2. Фільтруємо дані: беремо рядки, де є і Факт, і хоча б Прогноз сайту
    # На основі вашої бази (image_ada354.png), у нас вже є 489 рядків
    df_train = df_h.dropna(subset=['Fact_MW', 'Forecast_MW'])
    
    if len(df_train) < 20: # Поріг для старту
        return df_f['Forecast_MW'], 0.0, None, None

    # Навчання на наявних факторах
    X = df_train[existing_features].fillna(0)
    y = df_train['Fact_MW']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 3. Прогноз для головного графіка
    # Використовуємо ті ж колонки, що були в навчанні
    X_future = df_f[existing_features].fillna(0)
    predictions = model.predict(X_future)
    accuracy = model.score(X, y) * 100

    # 4. Аналітика для вкладки Навчання
    importance = pd.DataFrame({
        'Фактор': existing_features,
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    # Дельта для візуалізації
    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(100).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
