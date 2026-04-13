import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # Фактори, які ми шукаємо в базі (згідно з вашим скріншотом image_b9f574.png)
    features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
    
    # Вибираємо тільки ті рядки, де реально є ФАКТ (виробіток)
    # У вас таких рядків вже близько 300-400
    df_train = df_h.dropna(subset=['Fact_MW'])
    
    if len(df_train) < 24: # Достатньо хоча б однієї доби даних для старту
        return df_f['Forecast_MW'], 0.0, None, None

    # Заповнюємо пропуски в метеоданих середніми значеннями, щоб не втрачати рядки
    X = df_train[features].fillna(df_train[features].mean())
    y = df_train['Fact_MW']

    # Навчання моделі
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # Прогноз на майбутнє
    X_future = df_f[features].fillna(0)
    predictions = model.predict(X_future)
    accuracy = model.score(X, y) * 100

    # Аналітика для вкладки
    importance = pd.DataFrame({
        'Фактор': ['Сайт', 'Хмари', 'Темп.', 'Вітер', 'Опади'],
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(100).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
