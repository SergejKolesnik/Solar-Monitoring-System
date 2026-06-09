import pandas as pd
import numpy as np
import hashlib
import streamlit as st
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

BASE_CONST = 0.0114  # Rad -> MW константа collector.py

def _clean_numeric(df, columns):
    """Конвертуємо всi числовi колонки — виправляє порожнi рядки та текст з Google Sheets."""
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
    """Генеруємо хеш датафрейму — якщо данi не змiнились, модель не перенавчається."""
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
    # 1. Пiдготовка iсторичних даних
    df_h = df_h.copy()
    df_h['Time'] = pd.to_datetime(df_h['Time'], errors='coerce')
    df_h = df_h.dropna(subset=['Time'])

    numeric_cols = ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed',
                    'PrecipProb', 'Fact_MW', 'Capacity_MW']
    df_h = _clean_numeric(df_h, numeric_cols)

    # Вiдновлюємо Rad з Forecast_MW бази (Forecast_MW = Rad * 0.0114)
    # Це дає нам унiверсальну фiчу в одиницях Вт/м2 -- однаковий масштаб
    # i для навчання (df_h), i для прогнозу (df_f де Rad вже є напряму)
    df_h['Rad'] = df_h['Forecast_MW'] / BASE_CONST

    # Видаляємо аномалiї: Fact_MW не може перевищувати Capacity * 1.1
    df_h = df_h[
        (df_h['Fact_MW'] >= 0) &
        (df_h['Capacity_MW'] > 0) &
        (df_h['Fact_MW'] <= df_h['Capacity_MW'] * 1.1)
    ].copy()

    # Фiчi: Rad замiсть Forecast_MW -- масштаб однаковий мiж df_h i df_f
    target_features = ['Rad', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb', 'Capacity_MW']
    existing_features = [c for c in target_features if c in df_h.columns and c in df_f.columns]

    df_train = df_h[df_h['Fact_MW'].notna()].dropna(subset=[existing_features[0]])

    if len(df_train) < 20:
        # Fallback: проста формула Rad * BASE_CONST * kef
        cap = df_f['Capacity_MW'].iloc[0] if 'Capacity_MW' in df_f.columns else 12.5
        return (df_f['Rad'] * BASE_CONST * (cap / 12.5)).clip(lower=0), 0.0, None, None, 0.0, None

    # 2. Навчання (або з кешу)
    data_hash = _get_data_hash(df_train)
    model, X_test, y_test = _train_model(data_hash, df_train, existing_features)

    # 3. Оцiнка точностi
    test_preds = model.predict(X_test)
    accuracy_r2 = r2_score(y_test, test_preds) * 100
    mse_error = mean_squared_error(y_test, test_preds)

    # 4. Важливiсть факторiв
    importance = pd.DataFrame({
        'Фактор': existing_features,
        'Вплив %': (model.feature_importances_ * 100).round(1)
    }).sort_values(by='Вплив %', ascending=False)

    # 5. Scatter plot
    scatter_data = pd.DataFrame({
        'Факт': y_test.values,
        'План_ШI': test_preds
    })

    # 6. Аналiз за останнi 5 днiв де є факт АСКОЕ
    df_with_fact = df_train[df_train['Fact_MW'] > 0].sort_values('Time')
    if not df_with_fact.empty:
        last_fact_time = df_with_fact['Time'].max()
        window_start = last_fact_time - pd.Timedelta(days=5)
        hist_5d = df_with_fact[df_with_fact['Time'] >= window_start].copy()
    else:
        hist_5d = pd.DataFrame()

    if not hist_5d.empty:
        hist_5d['AI_Plan'] = model.predict(hist_5d[existing_features].fillna(0).astype(float))
        comparison_df = hist_5d.groupby(hist_5d['Time'].dt.date).agg({
            'Fact_MW': 'sum',
            'Forecast_MW': 'sum',
            'AI_Plan': 'sum'
        }).reset_index()
        comparison_df.columns = ['Дата', 'Факт (АСКОЕ)', 'Прогноз Сайту', 'План ШI']
    else:
        comparison_df = None

    # 7. Прогноз на майбутнє
    df_f_pred = df_f.copy()
    if 'Capacity_MW' not in df_f_pred.columns:
        df_f_pred['Capacity_MW'] = 12.5
    future_preds = model.predict(df_f_pred[existing_features].fillna(0).astype(float))
    future_preds = np.clip(future_preds, 0, None)

    return future_preds, accuracy_r2, importance, scatter_data, mse_error, comparison_df
