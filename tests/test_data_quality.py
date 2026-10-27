import importlib.util
from importlib.machinery import ModuleSpec
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd

if importlib.util.find_spec("sklearn") is None:
    sklearn_module = types.ModuleType("sklearn")
    ensemble_module = types.ModuleType("sklearn.ensemble")
    sklearn_module.__spec__ = ModuleSpec("sklearn", loader=None)
    ensemble_module.__spec__ = ModuleSpec("sklearn.ensemble", loader=None)

    class _UnusedHistGradientBoostingRegressor:
        pass

    ensemble_module.HistGradientBoostingRegressor = (
        _UnusedHistGradientBoostingRegressor
    )
    sklearn_module.ensemble = ensemble_module
    sys.modules["sklearn"] = sklearn_module
    sys.modules["sklearn.ensemble"] = ensemble_module

import collector
from dashboard_components import _month_fact_mwh
from data_quality import (
    localize_kyiv_timestamp,
    parse_local_timestamp,
    valid_fact_mask,
    valid_measurement_mask,
)


class FactValidationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 27, 12, 30)

    def test_valid_fact_mask_rejects_future_and_over_capacity_rows(self):
        frame = pd.DataFrame(
            {
                "Time": [
                    "2026-10-27 11:00:00",
                    "2026-10-29 11:00:00",
                    "2026-10-27 10:00:00",
                    "2026-10-27 09:00:00",
                ],
                "Fact_MW": [10.0, 5.0, 17.0, 0.0],
                "Capacity_MW": [15.2, 15.2, 15.2, 15.2],
            }
        )

        self.assertEqual(
            valid_fact_mask(frame, now=self.now).tolist(),
            [True, False, False, False],
        )

    def test_month_metric_uses_only_valid_fact_timestamps(self):
        frame = pd.DataFrame(
            {
                "Time": [
                    "2026-10-25 15:00:00",
                    "2026-10-26 12:00:00",
                    "2026-10-29 23:00:00",
                ],
                "Fact_MW": [8.0, 18.0, 0.0],
                "Capacity_MW": [15.2, 15.2, 15.2],
            }
        )

        total, latest = _month_fact_mwh(frame, self.now)

        self.assertEqual(total, 8.0)
        self.assertEqual(latest, pd.Timestamp("2026-10-25 15:00:00"))

    def test_update_facts_does_not_write_rejected_source_rows(self):
        base = collector.ensure_columns(
            pd.DataFrame({"Time": [pd.Timestamp("2026-10-27 09:00:00")]})
        )
        facts = [
            {"Time": datetime(2026, 10, 27, 11), "Fact_MW": 10.0},
            {"Time": datetime(2026, 10, 29, 11), "Fact_MW": 5.0},
            {"Time": datetime(2026, 10, 27, 10), "Fact_MW": 17.0},
        ]

        updated = collector.update_facts(
            base,
            facts,
            capacity_mw=15.2,
            now=self.now,
        )

        positive = updated[pd.to_numeric(updated["Fact_MW"], errors="coerce") > 0]
        self.assertEqual(len(positive), 1)
        self.assertEqual(positive.iloc[0]["Fact_MW"], 10.0)

    def test_zero_measurement_can_replace_stale_positive_value(self):
        base = collector.ensure_columns(
            pd.DataFrame(
                {
                    "Time": [pd.Timestamp("2026-10-27 11:00:00")],
                    "Fact_MW": [5.0],
                }
            )
        )

        updated = collector.update_facts(
            base,
            [{"Time": datetime(2026, 10, 27, 11), "Fact_MW": 0.0}],
            capacity_mw=15.2,
            now=self.now,
        )

        self.assertEqual(updated.iloc[0]["Fact_MW"], 0.0)

    def test_zero_is_valid_measurement_but_not_training_fact(self):
        frame = pd.DataFrame(
            {
                "Time": ["2026-10-27 11:00:00"],
                "Fact_MW": [0.0],
                "Capacity_MW": [15.2],
            }
        )

        self.assertTrue(valid_measurement_mask(frame, now=self.now).iloc[0])
        self.assertFalse(valid_fact_mask(frame, now=self.now).iloc[0])

    def test_calculate_errors_ignores_invalid_facts(self):
        frame = collector.ensure_columns(
            pd.DataFrame(
                {
                    "Time": [
                        pd.Timestamp("2026-10-27 11:00:00"),
                        pd.Timestamp("2026-10-27 10:00:00"),
                        pd.Timestamp("2026-10-29 11:00:00"),
                    ],
                    "Fact_MW": [10.0, 17.0, 5.0],
                    "Forecast_MW": [8.0, 8.0, 8.0],
                    "AI_Forecast_MW": [9.0, 9.0, 9.0],
                    "Capacity_MW": [15.2, 15.2, 15.2],
                }
            )
        )

        result = collector.calculate_errors(frame, now=self.now)

        self.assertEqual(result.loc[0, "Forecast_Error_MW"], 2.0)
        self.assertEqual(result.loc[1, "Forecast_Error_MW"], 0.0)
        self.assertEqual(result.loc[2, "Forecast_Error_MW"], 0.0)

    def test_chronological_gate_rejects_model_that_only_matches_baseline(self):
        times = pd.date_range("2026-07-01 12:00", periods=80, freq="D")
        frame = pd.DataFrame(
            {
                "Time": times,
                "Forecast_MW": 5.0,
                "Fact_MW": 6.0,
                "Forecast_Error_MW": 1.0,
                "Capacity_MW": 15.2,
            }
        )

        class ZeroCorrectionModel:
            def fit(self, features, target):
                return self

            def predict(self, features):
                return [0.0] * len(features)

        with patch.object(
            collector,
            "_new_correction_model",
            return_value=ZeroCorrectionModel(),
        ):
            accepted, metrics = collector._chronological_model_check(
                frame,
                ["Forecast_MW"],
            )

        self.assertFalse(accepted)
        self.assertAlmostEqual(metrics["ratio"], 1.0)

    def test_chronological_gate_accepts_model_with_real_holdout_gain(self):
        times = pd.date_range("2026-07-01 12:00", periods=80, freq="D")
        frame = pd.DataFrame(
            {
                "Time": times,
                "Forecast_MW": 5.0,
                "Fact_MW": 6.0,
                "Forecast_Error_MW": 1.0,
                "Capacity_MW": 15.2,
            }
        )

        class CorrectingModel:
            def fit(self, features, target):
                return self

            def predict(self, features):
                return [1.0] * len(features)

        with patch.object(
            collector,
            "_new_correction_model",
            return_value=CorrectingModel(),
        ):
            accepted, metrics = collector._chronological_model_check(
                frame,
                ["Forecast_MW"],
            )

        self.assertTrue(accepted)
        self.assertAlmostEqual(metrics["ai_mae"], 0.0)


class DstHandlingTests(unittest.TestCase):
    def test_dst_suffix_is_removed_before_parsing(self):
        self.assertEqual(
            parse_local_timestamp("2026-10-25 03:00:00 DST"),
            pd.Timestamp("2026-10-25 03:00:00"),
        )

    def test_repeated_hour_uses_explicit_dst_hint(self):
        daylight = localize_kyiv_timestamp("2026-10-25 03:00:00 DST")
        standard = localize_kyiv_timestamp("2026-10-25 03:00:00")

        self.assertEqual(daylight.utcoffset().total_seconds(), 3 * 3600)
        self.assertEqual(standard.utcoffset().total_seconds(), 2 * 3600)


if __name__ == "__main__":
    unittest.main()
