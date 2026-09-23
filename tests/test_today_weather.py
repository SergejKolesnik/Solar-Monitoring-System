import unittest

import pandas as pd

from today_weather import _format_compact_hourly_table, _format_hourly_table


class TodayWeatherTableTests(unittest.TestCase):
    def test_compact_table_keeps_solar_focused_columns(self):
        frame = pd.DataFrame(
            {
                "Time": pd.to_datetime(["2026-09-23 08:00"]),
                "temperature_2m": [18.5],
                "cloud_cover": [30],
                "shortwave_radiation": [420],
                "precipitation": [0.1],
                "wind_speed_10m": [2.4],
                "weather_code": [1],
                "pressure_msl": [1012],
            }
        )

        result = _format_compact_hourly_table(frame)

        self.assertEqual(
            list(result.columns),
            [
                "Температура, °C",
                "Хмарність, %",
                "Радіація, Вт/м²",
                "Опади, мм",
                "Вітер, м/с",
                "Час",
                "Стан",
            ],
        )
        self.assertNotIn("Тиск на рівні моря, гПа", result.columns)

    def test_format_hourly_table_keeps_hour_and_readable_status(self):
        frame = pd.DataFrame(
            {
                "Time": pd.to_datetime(["2026-09-23 08:00"]),
                "temperature_2m": [18.5],
                "weather_code": [1],
            }
        )

        result = _format_hourly_table(frame)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Час"], "08:00")
        self.assertNotIn("weather_code", result.columns)

    def test_format_hourly_table_tolerates_unknown_weather_code(self):
        frame = pd.DataFrame(
            {
                "Time": pd.to_datetime(["2026-09-23 08:00"]),
                "weather_code": [999],
            }
        )

        result = _format_hourly_table(frame)

        self.assertEqual(result.iloc[0]["Стан"], "—")


if __name__ == "__main__":
    unittest.main()
