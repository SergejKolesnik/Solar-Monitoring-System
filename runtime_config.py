"""Runtime configuration helpers shared by Streamlit and container hosting."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import streamlit as st


def get_secret(name: str, default: str | None = None) -> Any:
    """Read a secret from Streamlit Secrets, falling back to environment vars."""

    try:
        value = st.secrets.get(name)
    except Exception:
        value = None

    if value not in (None, ""):
        return value
    return os.getenv(name, default)


def get_json_secret(name: str) -> dict[str, Any]:
    """Read a JSON secret that may be stored as TOML object or JSON string."""

    value = get_secret(name)
    if not value:
        raise KeyError(f"{name} is not configured")
    if isinstance(value, dict):
        return dict(value)
    return json.loads(_normalize_json_secret_text(name, str(value)))


def _normalize_json_secret_text(name: str, value: str) -> str:
    """Normalize JSON copied from Streamlit TOML secrets into raw JSON text."""

    text = value.strip()

    assignment_match = re.match(rf"^{re.escape(name)}\s*=\s*(.+)$", text, re.DOTALL)
    if assignment_match:
        text = assignment_match.group(1).strip()

    for quote in ("'''", '"""'):
        if text.startswith(quote) and text.endswith(quote):
            return text[len(quote) : -len(quote)].strip()

    return text
