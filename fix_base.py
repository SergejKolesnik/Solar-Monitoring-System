from email_utils import *

def fix_anomalies(df):
    fixes = {
        'Forecast_MW': 15,
        'Fact_MW':     15,
        'CloudCover':  100,
        'Temp':        50,
        'WindSpeed':   35,
        'PrecipProb':  100,
    }
    for col, threshold in fixes.items():
        if col in df.columns:
            mask = df[col] > threshold
            df.loc[mask, col] = (df.loc[mask, col] / 10 if col in ('CloudCover','Temp','WindSpeed','PrecipProb') else df.loc[mask, col] / 1000).round(3)
            print(f"🔧 {col} виправлено: {mask.sum()} рядків")
    return df

def main():
    print(f"🚀 СТАРТ ПОВНОГО ВИПРАВЛЕННЯ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    sheet = get_sheet()
    df = load_df_from_sheet(sheet)
    print(f"📊 Завантажено: {len(df)} рядків")

    # Виправляємо аномалії
    df = fix_anomalies(df)

    # Обнуляємо факти і перечитуємо за 45 днів
    df['Fact_MW'] = 0.0
    print("🔄 Fact_MW обнулено — читаємо листи за 45 днів...")

    facts = read_facts_from_email(days=45)
    df = apply_facts(df, facts)

    # Оновлюємо погоду
    df = update_weather(df)

    # Capacity_MW
    df['Capacity_MW'] = 12.5

    # Фінальні діапазони
    print(f"\n📊 Фінальні діапазони:")
    for col in ['Forecast_MW', 'Fact_MW', 'Temp', 'WindSpeed', 'CloudCover']:
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors='coerce').dropna()
            non_zero = vals[vals > 0]
            print(f"   {col}: 0..{vals.max():.3f} (ненульових: {len(non_zero)})")

    save_df_to_sheet(sheet, df)
    print(f"\n🏁 Готово. Рядків: {len(df)}, Остання дата: {df['Time'].max()}")

if __name__ == "__main__":
    main()
