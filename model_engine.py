import pandas as pd
from sklearn.ensemble import RandomForestRegressor

def train_and_predict(df_history, df_forecast):
    """
    Головна функція навчання та прогнозування.
    """
    try:
        # Список ознак для навчання
        features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
        
        # 1. Підготовка даних для навчання
        # Видаляємо порожні рядки та беремо лише денну генерацію
        df_train = df_history.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
        df_train = df_train[df_train['Fact_MW'] > 0]
        
        # 2. Перевірка кількості даних
        if len(df_train) < 24:
            # Якщо даних замало, повертаємо прогноз сайту як масив
            return df_forecast['Forecast_MW'].values, 0.0
            
        # 3. Навчання моделі RandomForest
        model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
        model.fit(df_train[features].fillna(0), df_train['Fact_MW'])
        
        # 4. Розрахунок точності (R2)
        acc = 100 * model.score(df_train[features].fillna(0), df_train['Fact_MW'])
        
        # 5. Прогноз на основі нових метеоданих
        predictions = model.predict(df_forecast[features].fillna(0))
        
        return predictions, acc

    except Exception as e:
        print(f"Помилка в model_engine: {e}")
        # У разі будь-якої помилки повертаємо базовий прогноз
        return df_forecast['Forecast_MW'].values, 0.0
