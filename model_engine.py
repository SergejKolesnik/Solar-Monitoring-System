import pandas as pd
from sklearn.ensemble import RandomForestRegressor

def train_and_predict(df_history, df_forecast):
    """
    df_history: дані з solar_ai_base.csv
    df_forecast: свіжі дані з метеосервера
    """
    try:
        # Підготовка ознак (features)
        features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
        
        # Фільтруємо дані для навчання (тільки де є і факт, і прогноз)
        df_train = df_history.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
        df_train = df_train[df_train['Fact_MW'] > 0]
        
        if len(df_train) < 24:
            return df_forecast['Forecast_MW'], 0 # Мало даних для ШІ
            
        # Навчання моделі
        model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
        model.fit(df_train[features].fillna(0), df_train['Fact_MW'])
        
        # Розрахунок точності
        acc = 100 * model.score(df_train[features].fillna(0), df_train['Fact_MW'])
        
        # Прогноз ШІ
        predictions = model.predict(df_forecast[features].fillna(0))
        
        return predictions, acc
    except Exception as e:
        print(f"Помилка ШІ: {e}")
        return df_forecast['Forecast_MW'], 0
