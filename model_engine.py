import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor

def train_and_get_insights(df_h, df_f):
    # 1. Приводимо все до єдиного формату (видаляємо пробіли, малі літери)
    df_h.columns = df_h.columns.str.strip()
    df_f.columns = df_f.columns.str.strip()
    
    # Створюємо мапу для пошуку колонок незалежно від регістру
    h_cols = {c.lower(): c for c in df_h.columns}
    f_cols = {c.lower(): c for c in df_f.columns}
    
    # Фактори, які ми шукаємо
    targets = ['forecast_mw', 'cloudcover', 'temp', 'windspeed', 'precipprob']
    
    # Знаходимо колонки, які є В ОБОХ датафреймах
    existing_features = []
    for t in targets:
        if t in h_cols and t in f_cols:
            existing_features.append(h_cols[t]) # Беремо назву з бази
            
    # Якщо нічого не знайшли - беремо хоча б прогноз сайту
    if not existing_features:
        if 'Forecast_MW' in df_h.columns: existing_features = ['Forecast_MW']
        else: return df_f.get('Forecast_MW', pd.Series([0]*len(df_f))), 0.0, None, None

    # 2. Чистимо дані для навчання
    df_train = df_h.dropna(subset=['Fact_MW'] + existing_features)
    
    # Ваші 500 годин тепер точно пройдуть перевірку
    if len(df_train) < 10:
        return df_f[existing_features[0]] if not df_f.empty else pd.Series([0]*len(df_f)), 0.0, None, None

    # 3. Навчання
    X = df_train[existing_features].fillna(0)
    y = df_train['Fact_MW'].astype(float)

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)

    # 4. Прогноз
    # Для прогнозу беремо відповідні колонки з df_f
    f_feature_names = [f_cols[c.lower()] for c in existing_features]
    X_future = df_f[f_feature_names].fillna(0)
    predictions = model.predict(X_future)
    accuracy = model.score(X, y) * 100

    # Аналітика
    importance = pd.DataFrame({
        'Фактор': existing_features,
        'Важливість': model.feature_importances_
    }).sort_values(by='Важливість', ascending=False)

    error_df = df_train[['Time', 'Fact_MW', 'Forecast_MW']].tail(100).copy()
    error_df['Error'] = error_df['Fact_MW'] - error_df['Forecast_MW']
    
    return predictions, accuracy, importance, error_df
