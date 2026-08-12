"""Run the reviewed persistence path against the dedicated test spreadsheet."""

import json
import os
import sys
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

import collector  # noqa: E402


TEST_SHEET_ID = "1HY36aVyjAVfeRRD7oZNm1Cq5QFTYqOjFRlbO98djzNY"
EXPECTED_SPREADSHEET_TITLE = "Solar Monitoring — Persistence Integration Test"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _build_test_dataframe():
    timestamps = pd.to_datetime([
        "2026-08-12 08:00:00",
        "2026-08-12 09:00:00",
        "2026-08-12 10:00:00",
    ])
    data = {"Time": timestamps}
    for position, column in enumerate(collector.NUMERIC_COLS, start=1):
        data[column] = [position + offset / 10 for offset in range(3)]
    return pd.DataFrame(data)


def main():
    """Write synthetic data only to the hard-coded integration-test sheet."""
    credentials_json = os.getenv("GOOGLE_CREDENTIALS")
    if not credentials_json:
        print("ERROR: GOOGLE_CREDENTIALS is not set", file=sys.stderr)
        return 1

    try:
        credentials_info = json.loads(credentials_json)
        client_email = credentials_info.get("client_email")
        if not client_email:
            print("ERROR: client_email is missing", file=sys.stderr)
            return 1

        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=SCOPES,
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(TEST_SHEET_ID)

        if spreadsheet.id != TEST_SHEET_ID:
            raise RuntimeError("Unexpected spreadsheet ID")
        if spreadsheet.title != EXPECTED_SPREADSHEET_TITLE:
            raise RuntimeError("Unexpected spreadsheet title")

        production_sheet = spreadsheet.sheet1
        production_sheet_id = production_sheet.id
        production_sheet_title = production_sheet.title

        collector.save_df_to_sheet(
            spreadsheet,
            production_sheet,
            _build_test_dataframe(),
        )

        refreshed_production = spreadsheet.sheet1
        if refreshed_production.id != production_sheet_id:
            raise RuntimeError("Production sheet ID changed")
        if refreshed_production.title != production_sheet_title:
            raise RuntimeError("Production sheet title changed")
        if refreshed_production.index != 0:
            raise RuntimeError("Production sheet is no longer sheet1")

        staging_sheet = spreadsheet.worksheet(collector.STAGING_SHEET_NAME)
        if staging_sheet.id == production_sheet_id:
            raise RuntimeError("Staging unexpectedly replaced production")

        print(f"client_email={client_email}")
        print(f"spreadsheet_title={spreadsheet.title}")
        print(f"production_title={refreshed_production.title}")
        print(f"production_sheetId={refreshed_production.id}")
        print(f"production_index={refreshed_production.index}")
        print(f"staging_sheetId={staging_sheet.id}")
        print("write_smoke=PASS")
        return 0
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
