import os
import unittest
from unittest.mock import patch

from runtime_config import get_json_secret


class RuntimeConfigTests(unittest.TestCase):
    def test_get_json_secret_accepts_raw_json_env_value(self):
        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS": '{"type":"service_account"}'}, clear=False):
            self.assertEqual(
                get_json_secret("GOOGLE_CREDENTIALS"),
                {"type": "service_account"},
            )

    def test_get_json_secret_accepts_streamlit_toml_assignment(self):
        value = """GOOGLE_CREDENTIALS = '''{
  "type": "service_account",
  "project_id": "nzf-energy-reporter"
}'''"""
        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS": value}, clear=False):
            self.assertEqual(
                get_json_secret("GOOGLE_CREDENTIALS"),
                {"type": "service_account", "project_id": "nzf-energy-reporter"},
            )

    def test_get_json_secret_accepts_single_quoted_json_env_value(self):
        value = '\'{"type":"service_account","project_id":"nzf-energy-reporter"}\''
        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS": value}, clear=False):
            self.assertEqual(
                get_json_secret("GOOGLE_CREDENTIALS"),
                {"type": "service_account", "project_id": "nzf-energy-reporter"},
            )

    def test_get_json_secret_accepts_streamlit_toml_table(self):
        value = """
[google_service_account]
type = "service_account"
project_id = "nzf-energy-reporter"
"""
        with patch.dict(os.environ, {"GOOGLE_CREDENTIALS": value}, clear=False):
            self.assertEqual(
                get_json_secret("GOOGLE_CREDENTIALS"),
                {"type": "service_account", "project_id": "nzf-energy-reporter"},
            )


if __name__ == "__main__":
    unittest.main()
