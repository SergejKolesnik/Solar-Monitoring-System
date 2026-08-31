"""Runtime configuration helpers shared by Streamlit and container hosting."""

from __future__ import annotations

import json
import os
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
    return json.loads(str(value))
