"""Read-only connectivity smoke test for the dedicated test spreadsheet."""

import json
import os
import sys

import gspread
from google.oauth2.service_account import Credentials


TEST_SHEET_ID = "1HY36aVyjAVfeRRD7oZNm1Cq5QFTYqOjFRlbO98djzNY"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]


def main():
    """Open the test spreadsheet and print non-sensitive metadata only."""
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

        print(f"client_email={client_email}")

        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=SCOPES,
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(TEST_SHEET_ID)
        worksheet = spreadsheet.sheet1

        print(f"spreadsheet_title={spreadsheet.title}")
        print(f"worksheet_title={worksheet.title}")
        print(f"worksheet_index={worksheet.index}")
        print(f"worksheet_sheetId={worksheet.id}")
        return 0
    except Exception as exc:
        # Avoid printing exception details: auth libraries may attach request context.
        print(f"ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
