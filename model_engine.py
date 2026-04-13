import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split

def train_and_get_insights(df_h, df_f):
    # Готуємо дані для навчання
    features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # Видаляємо пропуски, щоб не "плутати" ШІ
    df_train = df_h.dropna(subset=features + ['Fact_MW'])
    
    if len(df_train) < 50: # Якщо даних мало для навчання
        return df_f['Forecast_MW'], 0, None, None

    X = df_train[features]
    y = df_train['Fact_MW']

    # Навчаємо модель
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 1. Робимо прогноз
    predictions = model.predict(df_f[features])

    # 2. Рахуємо точність (R2 score)
    accuracy = model.score(X, y) * 100

    # 3. Визначаємо важливість факторів (на чому "мозок" вчився)
    importance = pd.DataFrame({
        'Фактор': ['Прогноз сайту', 'Хмарність', 'Температура', 'Вітер', 'Опади'],
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    # 4. Аналіз помилки (Дельта)
    df_train['Error'] = df_train['Fact_MW'] - df_train['Forecast_MW']
    
    return predictions, accuracy, importance, df_train[['Time', 'Fact_MW', 'Forecast_MW', 'Error']].tail(100)
