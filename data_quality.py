"""Shared validation rules for SkyGrid operational fact data."""

from __future__ import annotations

import re
from datetime import datetime

import pandas as pd
import pytz


KYIV_TZ = pytz.timezone("Europe/Kyiv")
MIN_POSITIVE_FACT_MW = 0.05
MAX_CAPACITY_FACTOR = 1.10
FUTURE_FACT_TOLERANCE = pd.Timedelta(hours=1)
_TIMEZONE_SUFFIX = re.compile(r"\s+(DST|EEST|EET)\s*$", re.IGNORECASE)


def parse_local_timestamp(value) -> pd.Timestamp:
    """Return a timezone-naive Kyiv timestamp or ``NaT`` for invalid input."""

    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return pd.NaT

    cleaned = _TIMEZONE_SUFFIX.sub("", str(value).strip())
    timestamp = pd.to_datetime(cleaned, errors="coerce")
    if pd.isna(timestamp):
        return pd.NaT

    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is not None:
        return timestamp.tz_convert(KYIV_TZ).tz_localize(None)
    return timestamp


def parse_local_time_series(values: pd.Series) -> pd.Series:
    """Normalize a series of mixed timestamp values to naive Kyiv time."""

    return values.map(parse_local_timestamp)


def kyiv_now_naive() -> datetime:
    """Return the current Kyiv wall-clock time without timezone metadata."""

    return datetime.now(KYIV_TZ).replace(tzinfo=None)


def valid_fact_mask(
    df: pd.DataFrame,
    *,
    now=None,
    default_capacity_mw: float = 15.2,
    min_fact_mw: float = MIN_POSITIVE_FACT_MW,
    max_capacity_factor: float = MAX_CAPACITY_FACTOR,
) -> pd.Series:
    """Identify physically plausible, non-future positive generation facts.

    The raw Google Sheet remains unchanged. This mask is used consistently by
    model training, quality reporting, UI metrics, and shadow synchronization.
    A one-hour tolerance allows a completed hourly interval to be timestamped
    at its boundary without accepting rows from the forecast horizon.
    """

    if df.empty or "Time" not in df.columns or "Fact_MW" not in df.columns:
        return pd.Series(False, index=df.index, dtype=bool)

    times = parse_local_time_series(df["Time"])
    facts = pd.to_numeric(df["Fact_MW"], errors="coerce")

    if "Capacity_MW" in df.columns:
        capacity = pd.to_numeric(df["Capacity_MW"], errors="coerce")
    else:
        capacity = pd.Series(default_capacity_mw, index=df.index, dtype=float)
    capacity = capacity.where(capacity > 0, float(default_capacity_mw)).fillna(
        float(default_capacity_mw)
    )

    now_timestamp = parse_local_timestamp(now if now is not None else kyiv_now_naive())
    if pd.isna(now_timestamp):
        raise ValueError("now must be a valid timestamp")

    return (
        times.notna()
        & facts.gt(float(min_fact_mw))
        & facts.le(capacity * float(max_capacity_factor))
        & times.le(now_timestamp + FUTURE_FACT_TOLERANCE)
    )


def localize_kyiv_timestamp(value) -> pd.Timestamp:
    """Return an aware Kyiv timestamp with deterministic DST handling.

    FusionSolar may append ``DST`` to the repeated autumn hour. That suffix
    selects the daylight occurrence. Unmarked ambiguous hours use the standard
    time occurrence; nonexistent spring hours shift forward to the next valid
    local time. This keeps a single bad hour from aborting shadow sync.
    """

    raw = "" if value is None else str(value).strip()
    daylight_hint = bool(re.search(r"\s+(DST|EEST)\s*$", raw, re.IGNORECASE))
    timestamp = parse_local_timestamp(value)
    if pd.isna(timestamp):
        return pd.NaT
    if timestamp.tzinfo is not None:
        return timestamp.tz_convert(KYIV_TZ)
    return timestamp.tz_localize(
        KYIV_TZ,
        ambiguous=daylight_hint,
        nonexistent="shift_forward",
    )
