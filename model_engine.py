import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score

def train_and_get_insights(df_h, df_f):
    # 1. Підготовка даних
    df_h = df_h.copy()
    df_h['Time'] = pd.to_datetime(df_h['Time'], errors='coerce')
    df_h = df_h.dropna(subset=['Time'])
    
    target_features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    existing_features = [c for c in target_features if c in df_h.columns and c in df_f.columns]
    
    df_train = df_h.dropna(subset=['Fact_MW'] + [existing_features[0]])
    
    if len(df_train) < 20:
        return df_f['Forecast_MW'], 0.0, None, None, None, None

    # 2. Навчання моделі
    X = df_train[existing_features].fillna(0)
    y = df_train['Fact_MW'].astype(float)
    
    # Використовуємо 100 дерев
    model = RandomForestRegressor(n_estimators=100, random_state=42, warm_start=False)
    model.fit(X, y)

    # 3. Розрахунки точності
    train_preds = model.predict(X)
    accuracy_r2 = r2_score(y, train_preds) * 100 # Коефіцієнт детермінації
    mse_error = mean_squared_error(y, train_preds) # Середньоквадратична помилка

    # Коефіцієнти важливості (Feature Importance)
    importance = pd.DataFrame({
        'Фактор': existing_features, 
        'Вплив %': (model.feature_importances_ * 100).round(1)
    }).sort_values(by='Вплив %', ascending=False)

    # 4. Дані для Scatter Plot (Порівняння для графіку)
    scatter_data = pd.DataFrame({
        'Факт': y,
        'План_ШІ': train_preds
    })

    # 5. Аналіз за останні 5 днів
    hist_5d = df_train.tail(24 * 5).copy()
    hist_5d['AI_Plan'] = model.predict(hist_5d[existing_features].fillna(0))
    
    comparison_df = hist_5d.groupby(hist_5d['Time'].dt.date).agg({
        'Fact_MW': 'sum',
        'Forecast_MW': 'sum',
        'AI_Plan': 'sum'
    }).reset_index()
    comparison_df.columns = ['Дата', 'Факт (АСКОЕ)', 'Прогноз Сайту', 'План ШІ']

    # Прогноз на майбутнє
    future_preds = model.predict(df_f[existing_features].fillna(0))

    return future_preds, accuracy_r2, importance, scatter_data, mse_error, comparison_df
