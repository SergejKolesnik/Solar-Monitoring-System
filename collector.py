def sync():
    if os.path.exists(CSV_FILE):
        df_base = pd.read_csv(CSV_FILE)
        df_base['Time'] = pd.to_datetime(df_base['Time'])
    else:
        df_base = pd.DataFrame(columns=['Time', 'Fact_MW', 'Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb'])

    df_f = get_detailed_forecast()
    if not df_f.empty:
        for _, row in df_f.iterrows():
            mask = df_base['Time'] == row['Time']
            if mask.any():
                # ОНОВЛЕННЯ: якщо дані про погоду пусті (NaN) - заповнюємо їх
                if pd.isna(df_base.loc[mask, 'CloudCover']).any() or df_base.loc[mask, 'CloudCover'].iloc[0] == 0:
                    df_base.loc[mask, ['Forecast_MW', 'CloudCover', 'Temp', 'WindSpeed', 'PrecipProb']] = \
                        [row['Forecast_MW'], row['CloudCover'], row['Temp'], row['WindSpeed'], row['PrecipProb']]
            else:
                # Якщо години взагалі немає - додаємо новий рядок
                df_base = pd.concat([df_base, pd.DataFrame([row])], ignore_index=True)

    df_fact = get_fact_from_mail()
    if not df_fact.empty:
        for _, row in df_fact.iterrows():
            mask = df_base['Time'] == row['Time']
            if mask.any():
                df_base.loc[mask, 'Fact_MW'] = row['Fact_MW']

    # Фільтрація по поточному місяцю
    now = datetime.now(UA_TZ)
    df_base = df_base[(df_base['Time'].dt.year == now.year) & (df_base['Time'].dt.month == now.month)]
    
    df_base.sort_values('Time').drop_duplicates('Time').to_csv(CSV_FILE, index=False)
    print("Дані успішно оновлені та заповнені.")
