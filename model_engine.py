import pandas as pd
import numpy as np
import streamlit as st
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

# ── Константи ──────────────────────────────────────────────────────────────
BASE_CONST  = 0.0114   # Rad [Вт/м²] → MW для 12.5 МВт СЕС (з collector.py)
BASE_CAP_MW = 12.5     # Номiнальна потужнiсть СЕС у базi

# ── Утилiти ────────────────────────────────────────────────────────────────

def _to_numeric(series):
    return pd.to_numeric(
        series.astype(str).str.replace(',', '.', regex=False).str.strip(),
        errors='coerce'
    ).fillna(0)

def _add_time_features(df):
    """Додає Hour та Month з колонки Time."""
    df = df.copy()
    dt = pd.to_datetime(df['Time'], errors='coerce')
    df['Hour']  = dt.dt.hour
    df['Month'] = dt.dt.month
    return df

def _build_features(df, capacity_mw=None):
    """
    Формує матрицю фiч з сирих даних.
    Фiчi: Rad, CloudCover, Temp, WindSpeed, PrecipProb, Hour, Month, Capacity_MW
    """
    df = df.copy()

    # Rad: або є напряму (df_f), або вiдновлюємо з Forecast_MW бази (df_h)
    if 'Rad' not in df.columns:
        df['Rad'] = _to_numeric(df.get('Forecast_MW', pd.Series([0]*len(df), index=df.index))) / BASE_CONST

    for col in ['Rad', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']:
        if col in df.columns:
            df[col] = _to_numeric(df[col])
        else:
            df[col] = 0.0

    if capacity_mw is not None:
        df['Capacity_MW'] = float(capacity_mw)
    elif 'Capacity_MW' in df.columns:
        df['Capacity_MW'] = _to_numeric(df['Capacity_MW'])
        df.loc[df['Capacity_MW'] == 0, 'Capacity_MW'] = BASE_CAP_MW
    else:
        df['Capacity_MW'] = BASE_CAP_MW

    df = _add_time_features(df)

    FEATURES = ['Rad', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb',
                'Hour', 'Month', 'Capacity_MW']
    return df[FEATURES].fillna(0).astype(float)

def _clean_history(df_h):
    """
    Очищає iсторичнi данi для навчання:
    - тiльки денний час (5 <= Hour <= 21)
    - Fact_MW > 0
    - Fact_MW <= Capacity_MW * 1.05
    - Rad > 0
    """
    df = df_h.copy()
    df['Time']        = pd.to_datetime(df['Time'], errors='coerce')
    df['Fact_MW']     = _to_numeric(df.get('Fact_MW',     pd.Series([0]*len(df), index=df.index)))
    df['Capacity_MW'] = _to_numeric(df.get('Capacity_MW', pd.Series([BASE_CAP_MW]*len(df), index=df.index)))
    df.loc[df['Capacity_MW'] == 0, 'Capacity_MW'] = BASE_CAP_MW

    # Rad: або напряму, або з Forecast_MW
    if 'Rad' not in df.columns:
        df['Rad'] = _to_numeric(df.get('Forecast_MW', pd.Series([0]*len(df), index=df.index))) / BASE_CONST
    else:
        df['Rad'] = _to_numeric(df['Rad'])

    hour = df['Time'].dt.hour

    # Важливо: всi умови в окремих дужках!
    mask = (
        (df['Fact_MW'] > 0.01) &
        (df['Fact_MW'] <= df['Capacity_MW'] * 1.05) &
        (df['Rad'] > 5) &
        (hour >= 5) &
        (hour <= 21) &
        (df['Time'].notna())
    )
    return df[mask].copy()

# ── Основна функцiя ────────────────────────────────────────────────────────

def train_and_get_insights(df_h, df_f, capacity_mw=None):
    """
    Навчає GradientBoosting на iсторичних даних (df_h),
    будує прогноз на майбутнiй перiод (df_f).

    Повертає: (future_preds, accuracy_r2, importance_df,
               scatter_data, mse_error, comparison_df)
    """

    # ── 1. Пiдготовка тренувальних даних ──────────────────────────────────
    df_clean = _clean_history(df_h)

    if capacity_mw is None and 'Capacity_MW' in df_f.columns:
        capacity_mw = float(df_f['Capacity_MW'].iloc[0])
    if capacity_mw is None:
        capacity_mw = BASE_CAP_MW

    if len(df_clean) < 30:
        # Fallback: проста фiзична формула
        rad = _to_numeric(df_f.get('Rad', pd.Series([0]*len(df_f), index=df_f.index)))
        preds = (rad * BASE_CONST * (capacity_mw / BASE_CAP_MW)).clip(lower=0)
        return preds.values, 0.0, None, None, 0.0, None

    X_all = _build_features(df_clean, capacity_mw=None)
    y_all = df_clean['Fact_MW'].values

    # ── 2. Навчання / тест ─────────────────────────────────────────────────
    X_train, X_test, y_train, y_test = train_test_split(
        X_all, y_all, test_size=0.2, random_state=42, shuffle=True
    )

    model = GradientBoostingRegressor(
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        random_state=42
    )
    model.fit(X_train, y_train)

    # ── 3. Метрики ─────────────────────────────────────────────────────────
    test_preds  = model.predict(X_test)
    accuracy_r2 = r2_score(y_test, test_preds) * 100
    mse_error   = mean_squared_error(y_test, test_preds)

    # ── 4. Важливiсть факторiв ─────────────────────────────────────────────
    FEATURES = ['Rad', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb',
                'Hour', 'Month', 'Capacity_MW']
    importance = pd.DataFrame({
        'Фактор':  FEATURES,
        'Вплив %': (model.feature_importances_ * 100).round(1)
    }).sort_values('Вплив %', ascending=False)

    # ── 5. Scatter ─────────────────────────────────────────────────────────
    scatter_data = pd.DataFrame({'Факт': y_test, 'План_ШI': test_preds})

    # ── 6. Порiвняння за останнi 5 днiв ───────────────────────────────────
    last_time = df_clean['Time'].max()
    win_start = last_time - pd.Timedelta(days=5)
    hist_5d   = df_clean[df_clean['Time'] >= win_start].copy()

    comparison_df = None
    if not hist_5d.empty:
        X_hist = _build_features(hist_5d, capacity_mw=None)
        hist_5d = hist_5d.copy()
        hist_5d['AI_Plan'] = np.clip(model.predict(X_hist), 0, None)
        grp = hist_5d.groupby(hist_5d['Time'].dt.date)
        fact_sum     = grp['Fact_MW'].sum()
        ai_sum       = grp['AI_Plan'].sum()
        if 'Forecast_MW' in hist_5d.columns:
            fore_sum = grp['Forecast_MW'].sum()
        else:
            fore_sum = fact_sum * 0
        comparison_df = pd.DataFrame({
            'Дата':           fact_sum.index,
            'Факт (АСКОЕ)':   fact_sum.values,
            'Прогноз Сайту':  fore_sum.values,
            'План ШI':        ai_sum.values
        })

    # ── 7. Прогноз на майбутнє ─────────────────────────────────────────────
    X_future     = _build_features(df_f, capacity_mw=capacity_mw)
    future_preds = np.clip(model.predict(X_future), 0, capacity_mw)

    # Нiчнi години → 0
    df_f2 = df_f.copy()
    df_f2['Time'] = pd.to_datetime(df_f2['Time'], errors='coerce')
    night_mask = (df_f2['Time'].dt.hour < 5) | (df_f2['Time'].dt.hour > 21)
    future_preds[night_mask.values] = 0.0

    return future_preds, accuracy_r2, importance, scatter_data, mse_error, comparison_df
