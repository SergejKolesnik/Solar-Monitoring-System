import pandas as pd
import numpy as np
import hashlib
import streamlit as st
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

def _clean_numeric(df, columns):
    """Конвертуємо всі числові колонки — виправляє порожні рядки та текст з Google Sheets."""
    for col in columns:
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                .str.replace(',', '.', regex=False)
                .str.strip()
                .replace('', '0')
                .replace('nan', '0')
            )
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

def _get_data_hash(df_h: pd.DataFrame) -> str:
    """Генеруємо хеш датафрейму — якщо дані не змінились, модель не перенавчається."""
    return hashlib.md5(pd.util.hash_pandas_object(df_h).values).hexdigest()

@st.cache_resource
def _train_model(data_hash: str, df_h: pd.DataFrame, existing_features: list):
    """Навчання кешується — повторний виклик з тим самим hash поверне готову модель."""
    X = df_h[existing_features].fillna(0).astype(float)
    y = df_h['Fact_MW'].astype(float)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    return model, X_test, y_test

def train_and_get_insights(df_h, df_f):
    # 1. Підготовка даних
    df_h = df_h.copy()
    df_h['Time'] = pd.to_datetime(df_h['Time'], errors='coerce')
    df_h = df_h.dropna(subset=['Time'])

    # Числові колонки — очищуємо від текстових артефактів Google Sheets
    numeric_cols = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed',
                    'PrecipProb', 'Fact_MW', 'Capacity_MW']
    df_h = _clean_numeric(df_h, numeric_cols)

    target_features = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb', 'Capacity_MW']
    existing_features = [c for c in target_features if c in df_h.columns and c in df_f.columns]

    df_train = df_h[df_h['Fact_MW'] > 0].dropna(subset=['Fact_MW', existing_features[0]])

    if len(df_train) < 20:
        return df_f['Forecast_MW'], 0.0, None, None, 0.0, None

    # 2. Навчання (або з кешу)
    data_hash = _get_data_hash(df_train)
    model, X_test, y_test = _train_model(data_hash, df_train, existing_features)

    # 3. Чесна оцінка точності
    test_preds = model.predict(X_test)
    accuracy_r2 = r2_score(y_test, test_preds) * 100
    mse_error = mean_squared_error(y_test, test_preds)

    # 4. Важливість факторів
    importance = pd.DataFrame({
        'Фактор': existing_features,
        'Вплив %': (model.feature_importances_ * 100).round(1)
    }).sort_values(by='Вплив %', ascending=False)

    # 5. Scatter plot
    scatter_data = pd.DataFrame({
        'Факт': y_test.values,
        'План_ШІ': test_preds
    })

    # 6. Аналіз за останні 5 днів
    hist_5d = df_train.tail(24 * 5).copy()
    hist_5d['AI_Plan'] = model.predict(hist_5d[existing_features].fillna(0).astype(float))
    comparison_df = hist_5d.groupby(hist_5d['Time'].dt.date).agg({
        'Fact_MW': 'sum',
        'Forecast_MW': 'sum',
        'AI_Plan': 'sum'
    }).reset_index()
    comparison_df.columns = ['Дата', 'Факт (АСЬКЕ)', 'Прогноз Сайту', 'План ШІ']

    # 7. Прогноз на майбутнє
    future_preds = model.predict(df_f[existing_features].fillna(0).astype(float))

    return future_preds, accuracy_r2, importance, scatter_data, mse_error, comparison_df
