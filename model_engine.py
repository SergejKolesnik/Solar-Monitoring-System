import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # Фактори для навчання
    features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # ПЕРЕВІРКА: чи є колонки в базі?
    existing_features = [c for c in features if c in df_h.columns]
    
    # Якщо немає навіть базового прогнозу або мало даних - повертаємо прогноз сайту
    if 'Forecast_MW' not in existing_features or len(df_h[df_h['Fact_MW'].notna()]) < 20:
        return df_f['Forecast_MW'], 0.0, None, None

    # Навчаємо на тому, що є в наявності (щоб не було помилки index)
    df_train = df_h.dropna(subset=existing_features + ['Fact_MW'])
    
    if df_train.empty:
        return df_f['Forecast_MW'], 0.0, None, None

    X = df_train[existing_features]
    y = df_train['Fact_MW']

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # Для прогнозу на майбутнє теж використовуємо тільки наявні колонки
    predictions = model.predict(df_f[existing_features])
    accuracy = model.score(X, y) * 100

    # Аналітика для вкладки Навчання
    importance = pd.DataFrame({
        'Фактор': existing_features,
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(50).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
