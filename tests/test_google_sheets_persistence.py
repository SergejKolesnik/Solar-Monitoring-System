import importlib.util
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import pandas as pd


if importlib.util.find_spec("sklearn") is None:
    sklearn_module = types.ModuleType("sklearn")
    ensemble_module = types.ModuleType("sklearn.ensemble")

    class _UnusedHistGradientBoostingRegressor:
        pass

    ensemble_module.HistGradientBoostingRegressor = (
        _UnusedHistGradientBoostingRegressor
    )
    sklearn_module.ensemble = ensemble_module
    sys.modules["sklearn"] = sklearn_module
    sys.modules["sklearn.ensemble"] = ensemble_module

import collector


def _header():
    return ["Time", *collector.NUMERIC_COLS]


def _row(timestamp):
    return [timestamp, *(["0"] * len(collector.NUMERIC_COLS))]


class FakeWorksheet:
    def __init__(
        self,
        worksheet_id,
        values=None,
        row_count=100,
        col_count=20,
    ):
        self.id = worksheet_id
        self._values = values or []
        self.row_count = row_count
        self.col_count = col_count

    def get_all_values(self):
        return [row.copy() for row in self._values]

    def clear(self):
        self._values = []

    def resize(self, rows, cols):
        self.row_count = rows
        self.col_count = cols

    def update(self, values, range_name):
        start_row = int(range_name[1:]) - 1
        required_size = start_row + len(values)
        while len(self._values) < required_size:
            self._values.append([])
        for offset, row in enumerate(values):
            self._values[start_row + offset] = [str(value) for value in row]


class FakeSpreadsheet:
    def __init__(self, sheet1, staging=None, batch_error=None):
        self.sheet1 = sheet1
        self.batch_error = batch_error
        self.batch_requests = []
        self._worksheets = {}
        self._worksheets_by_id = {sheet1.id: sheet1}
        if staging is not None:
            self._worksheets[collector.STAGING_SHEET_NAME] = staging
            self._worksheets_by_id[staging.id] = staging

    def worksheet(self, title):
        try:
            return self._worksheets[title]
        except KeyError as exc:
            raise collector.gspread.exceptions.WorksheetNotFound(title) from exc

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(
            max(self._worksheets_by_id) + 1,
            row_count=rows,
            col_count=cols,
        )
        self._worksheets[title] = worksheet
        self._worksheets_by_id[worksheet.id] = worksheet
        return worksheet

    def batch_update(self, body):
        self.batch_requests.append(body)
        if self.batch_error:
            raise self.batch_error

        for request in body["requests"]:
            if "updateSheetProperties" in request:
                properties = request["updateSheetProperties"]["properties"]
                worksheet = self._worksheets_by_id[properties["sheetId"]]
                grid = properties["gridProperties"]
                worksheet.row_count = grid["rowCount"]
                worksheet.col_count = grid["columnCount"]
            elif "copyPaste" in request:
                copy_request = request["copyPaste"]
                source = self._worksheets_by_id[
                    copy_request["source"]["sheetId"]
                ]
                destination = self._worksheets_by_id[
                    copy_request["destination"]["sheetId"]
                ]
                row_count = copy_request["source"]["endRowIndex"]
                col_count = copy_request["source"]["endColumnIndex"]
                destination._values = [
                    row[:col_count]
                    for row in source.get_all_values()[:row_count]
                ]


class SheetValidationTests(unittest.TestCase):
    def test_successful_staging_validation(self):
        values = [
            _header(),
            _row("2026-08-10 08:00:00"),
            _row("2026-08-10 09:00:00"),
        ]

        collector._validate_sheet_values(
            values,
            expected_header=_header(),
            expected_row_count=2,
            expected_first_time="2026-08-10 08:00:00",
            expected_last_time="2026-08-10 09:00:00",
        )

    def test_wrong_row_count_is_rejected(self):
        values = [_header(), _row("2026-08-10 08:00:00")]

        with self.assertRaisesRegex(ValueError, "Row count mismatch"):
            collector._validate_sheet_values(
                values,
                expected_header=_header(),
                expected_row_count=2,
                expected_first_time="2026-08-10 08:00:00",
                expected_last_time="2026-08-10 09:00:00",
            )

    def test_wrong_header_is_rejected(self):
        wrong_header = _header().copy()
        wrong_header[0] = "Timestamp"

        with self.assertRaisesRegex(ValueError, "Header mismatch"):
            collector._validate_sheet_values(
                [wrong_header, _row("2026-08-10 08:00:00")],
                expected_header=_header(),
                expected_row_count=1,
                expected_first_time="2026-08-10 08:00:00",
                expected_last_time="2026-08-10 08:00:00",
            )

    def test_duplicate_time_is_rejected(self):
        values = [
            _header(),
            _row("2026-08-10 08:00:00"),
            _row("2026-08-10 08:00:00"),
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate Time"):
            collector._validate_sheet_values(
                values,
                expected_header=_header(),
                expected_row_count=2,
                expected_first_time="2026-08-10 08:00:00",
                expected_last_time="2026-08-10 08:00:00",
            )


class SheetPromotionTests(unittest.TestCase):
    def test_save_df_to_sheet_successful_end_to_end(self):
        production_id = 10
        production = FakeWorksheet(
            production_id,
            values=[["old-header"], ["old-value"]],
            row_count=100,
            col_count=20,
        )
        staging = FakeWorksheet(20, row_count=100, col_count=20)
        spreadsheet = FakeSpreadsheet(production, staging=staging)
        df = pd.DataFrame({
            "Time": [
                pd.Timestamp("2026-08-10 08:00:00"),
                pd.Timestamp("2026-08-10 09:00:00"),
            ],
            "Forecast_MW": [1.1, 1.2],
            "Fact_MW": [1.0, 1.1],
        })

        collector.save_df_to_sheet(spreadsheet, production, df)

        self.assertEqual(len(spreadsheet.batch_requests), 1)
        self.assertEqual(production.id, production_id)
        self.assertIs(spreadsheet.sheet1, production)
        production_values = production.get_all_values()
        collector._validate_sheet_values(
            production_values,
            expected_header=_header(),
            expected_row_count=2,
            expected_first_time="2026-08-10 08:00:00",
            expected_last_time="2026-08-10 09:00:00",
        )
        self.assertEqual(staging.get_all_values(), production_values)

    def test_promotion_uses_one_atomic_batch_and_preserves_production_id(self):
        production = FakeWorksheet(10, row_count=50, col_count=15)
        staging = FakeWorksheet(20, row_count=50, col_count=15)
        spreadsheet = FakeSpreadsheet(production, staging=staging)

        collector._promote_staging_to_production(
            spreadsheet,
            production_sheet=production,
            staging_sheet=staging,
            required_rows=10,
            required_cols=5,
        )

        self.assertEqual(production.id, 10)
        self.assertEqual(staging.id, 20)
        self.assertEqual(len(spreadsheet.batch_requests), 1)
        requests_payload = spreadsheet.batch_requests[0]["requests"]
        self.assertEqual(len(requests_payload), 2)
        self.assertEqual(
            requests_payload[0]["updateCells"]["range"]["sheetId"],
            10,
        )
        copy_request = requests_payload[1]["copyPaste"]
        self.assertEqual(copy_request["source"]["sheetId"], 20)
        self.assertEqual(copy_request["destination"]["sheetId"], 10)
        self.assertEqual(copy_request["pasteType"], "PASTE_VALUES")

    def test_promotion_grid_expansion_is_in_the_same_atomic_batch(self):
        production = FakeWorksheet(10, row_count=5, col_count=3)
        staging = FakeWorksheet(20, row_count=20, col_count=10)
        spreadsheet = FakeSpreadsheet(production, staging=staging)

        collector._promote_staging_to_production(
            spreadsheet,
            production_sheet=production,
            staging_sheet=staging,
            required_rows=10,
            required_cols=5,
        )

        self.assertEqual(len(spreadsheet.batch_requests), 1)
        requests_payload = spreadsheet.batch_requests[0]["requests"]
        self.assertEqual(len(requests_payload), 3)
        self.assertIn("updateSheetProperties", requests_payload[0])
        self.assertIn("updateCells", requests_payload[1])
        self.assertIn("copyPaste", requests_payload[2])
        grid = requests_payload[0]["updateSheetProperties"]["properties"][
            "gridProperties"
        ]
        self.assertEqual(grid, {"rowCount": 10, "columnCount": 5})
        self.assertEqual(
            requests_payload[1]["updateCells"]["range"]["sheetId"],
            production.id,
        )
        self.assertEqual(
            requests_payload[2]["copyPaste"]["destination"]["sheetId"],
            production.id,
        )

    def test_promotion_api_exception_propagates(self):
        production = FakeWorksheet(10)
        staging = FakeWorksheet(20)
        spreadsheet = FakeSpreadsheet(
            production,
            batch_error=RuntimeError("Google API unavailable"),
        )

        with self.assertRaisesRegex(RuntimeError, "Google API unavailable"):
            collector._promote_staging_to_production(
                spreadsheet,
                production_sheet=production,
                staging_sheet=staging,
                required_rows=10,
                required_cols=5,
            )

        self.assertEqual(production.id, 10)
        self.assertEqual(len(spreadsheet.batch_requests), 1)

    def test_staging_failure_does_not_promote(self):
        production = FakeWorksheet(10)
        staging = FakeWorksheet(20, values=[["wrong-header"]])
        spreadsheet = FakeSpreadsheet(production)
        df = pd.DataFrame({"Time": [pd.Timestamp("2026-08-10 08:00:00")]})

        with (
            patch.object(
                collector,
                "_get_or_create_staging_sheet",
                return_value=staging,
            ),
            patch.object(collector, "_write_staging_sheet"),
        ):
            with self.assertRaisesRegex(ValueError, "Header mismatch"):
                collector.save_df_to_sheet(spreadsheet, production, df)

        self.assertEqual(spreadsheet.batch_requests, [])


class PipelineFailureTests(unittest.TestCase):
    def test_supabase_is_not_called_after_google_sheets_failure(self):
        production = FakeWorksheet(10)
        spreadsheet = FakeSpreadsheet(production)
        run_time = datetime(2026, 8, 11, 20, 0, 0)
        df = pd.DataFrame({
            "Time": [run_time],
            "Forecast_MW": [1.0],
            "Fact_MW": [1.0],
            "AI_Forecast_MW": [1.0],
        })
        supabase_sync = Mock()

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 8, 11, 20, 0, 0)

        with (
            patch.object(collector, "datetime", FixedDateTime),
            patch.object(collector, "get_spreadsheet", return_value=spreadsheet),
            patch.object(
                collector,
                "load_capacity_from_settings",
                return_value=12.5,
            ),
            patch.object(collector, "load_df_from_sheet", return_value=df),
            patch.object(collector, "read_facts_from_email", return_value=[]),
            patch.object(collector, "update_facts", return_value=df),
            patch.object(collector, "update_weather", return_value=df),
            patch.object(collector, "log_data_quality"),
            patch.object(collector, "calculate_errors", return_value=df),
            patch.object(
                collector,
                "save_df_to_sheet",
                side_effect=RuntimeError("promotion failed"),
            ),
            patch.object(
                collector,
                "sync_to_supabase_shadow",
                supabase_sync,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "promotion failed"):
                collector.main()

        supabase_sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
