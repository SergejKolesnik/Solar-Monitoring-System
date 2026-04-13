import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    """
    Навчає модель на існуючій базі та повертає прогноз і аналітику факторів.
    """
    # Список факторів, які ми використовуємо для аналізу
    features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # Визначаємо, які з цих колонок реально існують у файлі
    existing_features = [c for c in features if c in df_h.columns]
    
    # Відбираємо тільки ті рядки, де є Фактичний виробіток (Fact_MW)
    df_train = df_h.dropna(subset=['Fact_MW'])
    
    # Якщо даних замало для навчання (менше доби), повертаємо стандартний прогноз
    if len(df_train) < 24:
        return df_f['Forecast_MW'], 0.0, None, None

    # Готуємо дані (заповнюємо рідкісні пропуски в метеоданих нулями)
    X = df_train[existing_features].fillna(0)
    y = df_train['Fact_MW']

    # Ініціалізуємо та навчаємо модель "Випадкового лісу"
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # Робимо прогноз на майбутнє (df_f - це прогноз погоди)
    X_future = df_f[existing_features].fillna(0)
    predictions = model.predict(X_future)
    
    # Рахуємо точність моделі на тренувальних даних
    accuracy = model.score(X, y) * 100

    # Створюємо таблицю важливості факторів для візуалізації
    importance = pd.DataFrame({
        'Фактор': existing_features,
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    # Готуємо дані для графіка Дельти (Помилка сайту за останні 100 годин)
    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(100).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
