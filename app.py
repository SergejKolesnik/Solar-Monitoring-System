@st.cache_data(ttl=3600)
def get_weather_data_vc():
    api_key = st.secrets["WEATHER_API_KEY"]
    # Координати Нікополя
    lat, lon = "47.56", "34.39"
    url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/next7days?unitGroup=metric&elements=datetime,temp,cloudcover,solarradiation,precip&include=hours&key={api_key}&contentType=json"
    
    try:
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data = res.json()
        
        hours_list = []
        for day in data['days']:
            for hr in day['hours']:
                # Об'єднуємо дату та час
                full_time = f"{day['datetime']} {hr['datetime']}"
                hours_list.append({
                    'Time': pd.to_datetime(full_time),
                    'Radiation': hr.get('solarradiation', 0),
                    'Clouds': hr.get('cloudcover', 0),
                    'Temp': hr.get('temp', 0),
                    'Rain': hr.get('precip', 0)
                })
        
        df = pd.DataFrame(hours_list)
        # Розрахунок генерації (коефіцієнти адаптовані під Visual Crossing)
        df['Base_MW'] = df['Radiation'] * 11.4 * 0.00095 * (1 - df['Clouds']/100 * 0.15)
        return df
    except Exception as e:
        return f"ERROR: {str(e)}"
