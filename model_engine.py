import pandas as pd
from sklearn.ensemble import RandomForestRegressor

def train_and_predict(df_history, df_forecast):
    try:
        features = ['Hour', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']
        df_train = df_history.dropna(subset=['Fact_MW', 'Forecast_MW']).copy()
        df_train = df_train[df_train['Fact_MW'] > 0]
        
        if len(df_train) < 24:
            return df_forecast['Forecast_MW'].values, 0.0
            
        model = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
        model.fit(df_train[features].fillna(0), df_train['Fact_MW'])
        acc = 100 * model.score(df_train[features].fillna(0), df_train['Fact_MW'])
        preds = model.predict(df_forecast[features].fillna(0))
        return preds, acc
    except:
        return df_forecast['Forecast_MW'].values, 0.0
