import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # Фактори, які ми хочемо бачити
    desired_features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # 1. Вибираємо ТІЛЬКИ ті колонки, які реально є у вашому CSV
    existing_features = [c for c in desired_features if c in df_h.columns]
    
    # 2. Відбираємо рядки, де заповнений ФАКТ (виробіток)
    df_train = df_h.dropna(subset=['Fact_MW'])
    
    # Знижуємо поріг до 20 годин, щоб ви побачили результат вже сьогодні
    if len(df_train) < 20:
        return df_f['Forecast_MW'], 0.0, None, None

    # 3. Готуємо дані для навчання (заповнюємо пусті клітинки середнім, щоб не втрачати рядки)
    X = df_train[existing_features].fillna(df_train[existing_features].mean())
    y = df_train['Fact_MW']

    # 4. Навчання моделі
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 5. Прогноз на майбутнє
    X_future = df_f[existing_features].fillna(0)
    predictions = model.predict(X_future)
    accuracy = model.score(X, y) * 100

    # 6. Важливість факторів (для графіків у вкладці Навчання)
    importance = pd.DataFrame({
        'Фактор': existing_features,
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    # Історія помилок (дельта)
    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(100).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
