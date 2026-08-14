"""Read-only forecast quality report for SkyGrid Solar AI.

The report downloads the public CSV export of the production Google Sheet and
compares the base weather forecast with the saved AI forecast. It does not write
to Google Sheets, Supabase, or local project data.
"""

from __future__ import annotations

import argparse
import io
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests


DEFAULT_SHEET_ID = "1ckVoJla9DA3BLQfBDy30sXmaOyH2HSqCZ1FbZtUDr9Q"
DEFAULT_GID = "0"
NUMERIC_COLUMNS = [
    "Forecast_MW",
    "CloudCover",
    "Temp",
    "WindSpeed",
    "PrecipProb",
    "Fact_MW",
    "Capacity_MW",
    "AI_Forecast_MW",
]


@dataclass(frozen=True)
class QualityWindow:
    """Aggregated forecast quality for one recent time window."""

    label: str
    days: int
    start_date: object
    end_date: object
    base_daily_mape: float
    ai_daily_mape: float
    improvement_pct: float
    ai_better_days_pct: float
    base_bias_mwh: float
    ai_bias_mwh: float


@dataclass(frozen=True)
class HourlyQualityWindow:
    """Hourly forecast quality for operational next-day planning."""

    label: str
    hours: int
    start_time: object
    end_time: object
    base_mae_mw: float
    ai_mae_mw: float
    improvement_pct: float
    base_rmse_mw: float
    ai_rmse_mw: float
    base_p90_abs_mw: float
    ai_p90_abs_mw: float
    base_bias_mw: float
    ai_bias_mw: float
    ai_better_hours_pct: float


def build_csv_url(sheet_id: str, gid: str) -> str:
    """Return the public CSV export URL for a Google Sheets tab."""

    return (
        "https://docs.google.com/spreadsheets/d/"
        f"{sheet_id}/export?format=csv&gid={gid}"
    )


def load_sheet_csv(url: str) -> pd.DataFrame:
    """Download and parse a Google Sheets CSV export."""

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize dates and numeric columns used by the report."""

    prepared = df.copy()
    prepared["Time"] = pd.to_datetime(prepared["Time"], errors="coerce")
    prepared = prepared.dropna(subset=["Time"]).sort_values("Time")

    for column in NUMERIC_COLUMNS:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    for column in ["Forecast_MW", "Fact_MW", "AI_Forecast_MW"]:
        if column not in prepared.columns:
            prepared[column] = 0.0
        prepared[column] = prepared[column].fillna(0.0)

    return prepared


def build_daily_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hourly rows into daily MWh quality metrics."""

    daily_source = df.copy()
    daily_source["Date"] = daily_source["Time"].dt.date
    daily_source["Has_Fact"] = daily_source["Fact_MW"] > 0.05

    daily = daily_source.groupby("Date").agg(
        Fact_MWh=("Fact_MW", "sum"),
        Base_MWh=("Forecast_MW", "sum"),
        AI_MWh=("AI_Forecast_MW", "sum"),
        Fact_Hours=("Has_Fact", "sum"),
        Cloud_Avg=("CloudCover", "mean"),
        Cloud_Max=("CloudCover", "max"),
        Precip_Max=("PrecipProb", "max"),
    ).reset_index()

    daily = daily[
        (daily["Fact_MWh"] > 1.0)
        & (daily["Base_MWh"] > 1.0)
        & (daily["Fact_Hours"] >= 4)
    ].copy()
    if daily.empty:
        return daily

    daily["Base_Error_MWh"] = daily["Base_MWh"] - daily["Fact_MWh"]
    daily["AI_Error_MWh"] = daily["AI_MWh"] - daily["Fact_MWh"]
    daily["Base_Daily_MAPE"] = (
        daily["Base_Error_MWh"].abs() / daily["Fact_MWh"] * 100
    )
    daily["AI_Daily_MAPE"] = (
        daily["AI_Error_MWh"].abs() / daily["Fact_MWh"] * 100
    )
    daily["AI_Better"] = daily["AI_Daily_MAPE"] < daily["Base_Daily_MAPE"]
    return daily


def summarize_window(daily: pd.DataFrame, days: int) -> QualityWindow | None:
    """Build one trailing-window quality summary."""

    if daily.empty:
        return None

    end_date = pd.Timestamp(daily["Date"].max())
    start_cutoff = end_date - pd.Timedelta(days=days - 1)
    window = daily[pd.to_datetime(daily["Date"]) >= start_cutoff].copy()
    if window.empty:
        return None

    base_mape = float(window["Base_Daily_MAPE"].mean())
    ai_mape = float(window["AI_Daily_MAPE"].mean())
    improvement = 100 * (base_mape - ai_mape) / base_mape if base_mape else 0.0

    return QualityWindow(
        label=f"last_{days}_days",
        days=int(len(window)),
        start_date=window["Date"].min(),
        end_date=window["Date"].max(),
        base_daily_mape=base_mape,
        ai_daily_mape=ai_mape,
        improvement_pct=improvement,
        ai_better_days_pct=float(window["AI_Better"].mean() * 100),
        base_bias_mwh=float(window["Base_Error_MWh"].mean()),
        ai_bias_mwh=float(window["AI_Error_MWh"].mean()),
    )


def build_hourly_quality(df: pd.DataFrame) -> pd.DataFrame:
    """Build per-hour quality rows for the productive daylight period."""

    hourly = df[
        (df["Fact_MW"] > 0.05)
        & (df["Forecast_MW"] > 0.05)
        & (df["AI_Forecast_MW"] > 0.05)
    ].copy()
    if hourly.empty:
        return hourly

    hourly["Date"] = hourly["Time"].dt.date
    hourly["Hour"] = hourly["Time"].dt.hour
    hourly["Base_Error_MW"] = hourly["Forecast_MW"] - hourly["Fact_MW"]
    hourly["AI_Error_MW"] = hourly["AI_Forecast_MW"] - hourly["Fact_MW"]
    hourly["Base_Abs_Error_MW"] = hourly["Base_Error_MW"].abs()
    hourly["AI_Abs_Error_MW"] = hourly["AI_Error_MW"].abs()
    hourly["AI_Better"] = hourly["AI_Abs_Error_MW"] < hourly["Base_Abs_Error_MW"]
    return hourly


def summarize_hourly_window(
    hourly: pd.DataFrame,
    days: int,
    label: str | None = None,
) -> HourlyQualityWindow | None:
    """Build one trailing-window hourly quality summary."""

    if hourly.empty:
        return None

    end_date = pd.Timestamp(hourly["Date"].max())
    start_cutoff = end_date - pd.Timedelta(days=days - 1)
    window = hourly[pd.to_datetime(hourly["Date"]) >= start_cutoff].copy()
    if window.empty:
        return None

    base_mae = float(window["Base_Abs_Error_MW"].mean())
    ai_mae = float(window["AI_Abs_Error_MW"].mean())
    improvement = 100 * (base_mae - ai_mae) / base_mae if base_mae else 0.0

    return HourlyQualityWindow(
        label=label or f"last_{days}_days_hourly",
        hours=int(len(window)),
        start_time=window["Time"].min(),
        end_time=window["Time"].max(),
        base_mae_mw=base_mae,
        ai_mae_mw=ai_mae,
        improvement_pct=improvement,
        base_rmse_mw=float(np.sqrt((window["Base_Error_MW"] ** 2).mean())),
        ai_rmse_mw=float(np.sqrt((window["AI_Error_MW"] ** 2).mean())),
        base_p90_abs_mw=float(window["Base_Abs_Error_MW"].quantile(0.90)),
        ai_p90_abs_mw=float(window["AI_Abs_Error_MW"].quantile(0.90)),
        base_bias_mw=float(window["Base_Error_MW"].mean()),
        ai_bias_mw=float(window["AI_Error_MW"].mean()),
        ai_better_hours_pct=float(window["AI_Better"].mean() * 100),
    )


def build_shadow_quality(
    df: pd.DataFrame,
    lookback_days: int = 30,
    min_samples: int = 6,
) -> pd.DataFrame:
    """Evaluate the current cloud-bucket shadow correction on historical rows."""

    required = {"Time", "Fact_MW", "Forecast_MW", "AI_Forecast_MW", "CloudCover"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    shadow = df[
        (df["Fact_MW"] > 0.05)
        & (df["Forecast_MW"] > 0.05)
        & (df["AI_Forecast_MW"] > 0.05)
    ].copy()
    if shadow.empty:
        return pd.DataFrame()

    shadow["Date"] = shadow["Time"].dt.date
    shadow["Cloud_Bucket"] = pd.cut(
        shadow["CloudCover"].fillna(0).clip(0, 100),
        bins=[-0.1, 25, 50, 75, 100],
        labels=["0-25", "25-50", "50-75", "75-100"],
    )

    rows = []
    for index, row in shadow.iterrows():
        history_start = row["Time"] - pd.Timedelta(days=lookback_days)
        history = shadow[
            (shadow["Time"] < row["Time"])
            & (shadow["Time"] >= history_start)
            & (shadow["Cloud_Bucket"] == row["Cloud_Bucket"])
        ]
        if len(history) < min_samples:
            history = shadow[
                (shadow["Time"] < row["Time"])
                & (shadow["Time"] >= history_start)
            ]
        if len(history) < min_samples:
            continue

        ratios = (
            history["Fact_MW"]
            / history["AI_Forecast_MW"].replace(0, np.nan)
        ).replace([np.inf, -np.inf], np.nan).dropna()
        if ratios.empty:
            continue

        factor = float(np.clip(ratios.median(), 0.70, 1.30))
        exp_mw = float(row["AI_Forecast_MW"] * factor)
        cap = float(row.get("Capacity_MW", 0) or 0)
        if cap > 0:
            exp_mw = min(exp_mw, cap * 1.05)

        rows.append({
            "Time": row["Time"],
            "Date": row["Date"],
            "Fact_MW": row["Fact_MW"],
            "Base_MW": row["Forecast_MW"],
            "AI_MW": row["AI_Forecast_MW"],
            "Shadow_MW": max(0.0, exp_mw),
            "Shadow_Factor": factor,
            "Samples": len(history),
        })

    hourly = pd.DataFrame(rows)
    if hourly.empty:
        return hourly

    daily = hourly.groupby("Date").agg(
        Fact_MWh=("Fact_MW", "sum"),
        Base_MWh=("Base_MW", "sum"),
        AI_MWh=("AI_MW", "sum"),
        Shadow_MWh=("Shadow_MW", "sum"),
        Hours=("Fact_MW", "size"),
        Shadow_Factor=("Shadow_Factor", "mean"),
        Samples=("Samples", "mean"),
    ).reset_index()
    daily = daily[(daily["Fact_MWh"] > 1.0) & (daily["Hours"] >= 4)].copy()
    if daily.empty:
        return daily

    for name, column in [
        ("Base_Daily_MAPE", "Base_MWh"),
        ("AI_Daily_MAPE", "AI_MWh"),
        ("Shadow_Daily_MAPE", "Shadow_MWh"),
    ]:
        daily[name] = (daily[column] - daily["Fact_MWh"]).abs() / daily["Fact_MWh"] * 100

    daily["Shadow_Better_AI"] = daily["Shadow_Daily_MAPE"] < daily["AI_Daily_MAPE"]
    return daily


def print_window(summary: QualityWindow) -> None:
    """Print a compact human-readable quality window."""

    print(
        f"{summary.label}: {summary.start_date}..{summary.end_date} "
        f"({summary.days} days)"
    )
    print(
        "  daily MAPE: "
        f"base={summary.base_daily_mape:.1f}% "
        f"ai={summary.ai_daily_mape:.1f}% "
        f"improvement={summary.improvement_pct:+.1f}% "
        f"ai_better_days={summary.ai_better_days_pct:.0f}%"
    )
    print(
        "  daily bias: "
        f"base={summary.base_bias_mwh:+.1f} MWh/day "
        f"ai={summary.ai_bias_mwh:+.1f} MWh/day"
    )


def print_hourly_window(summary: HourlyQualityWindow) -> None:
    """Print a compact human-readable hourly quality window."""

    print(
        f"{summary.label}: {summary.start_time}..{summary.end_time} "
        f"({summary.hours} productive hours)"
    )
    print(
        "  hourly MAE: "
        f"base={summary.base_mae_mw:.2f} MW "
        f"ai={summary.ai_mae_mw:.2f} MW "
        f"improvement={summary.improvement_pct:+.1f}% "
        f"ai_better_hours={summary.ai_better_hours_pct:.0f}%"
    )
    print(
        "  hourly RMSE: "
        f"base={summary.base_rmse_mw:.2f} MW "
        f"ai={summary.ai_rmse_mw:.2f} MW"
    )
    print(
        "  p90 abs error: "
        f"base={summary.base_p90_abs_mw:.2f} MW "
        f"ai={summary.ai_p90_abs_mw:.2f} MW"
    )
    print(
        "  hourly bias: "
        f"base={summary.base_bias_mw:+.2f} MW "
        f"ai={summary.ai_bias_mw:+.2f} MW"
    )


def main() -> int:
    """Run the read-only quality report."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    parser.add_argument("--gid", default=DEFAULT_GID)
    args = parser.parse_args()

    df = prepare_frame(load_sheet_csv(build_csv_url(args.sheet_id, args.gid)))
    daily = build_daily_quality(df)
    hourly = build_hourly_quality(df)

    facts = df[df["Fact_MW"] > 0.05]
    print(f"rows={len(df)}")
    print(f"data_range={df['Time'].min()}..{df['Time'].max()}")
    if not facts.empty:
        print(f"fact_range={facts['Time'].min()}..{facts['Time'].max()}")
    print()

    for days in [7, 14, 30]:
        summary = summarize_window(daily, days)
        if summary:
            print_window(summary)
    print()

    print("hourly_quality:")
    for days in [7, 14, 30]:
        summary = summarize_hourly_window(hourly, days)
        if summary:
            print_hourly_window(summary)
    print()

    print("hourly_blocks_last_14_days:")
    hour_blocks = {
        "morning_06_09": (6, 9),
        "solar_peak_10_15": (10, 15),
        "evening_16_20": (16, 20),
    }
    for label, (start_hour, end_hour) in hour_blocks.items():
        block = hourly[
            (hourly["Hour"] >= start_hour)
            & (hourly["Hour"] <= end_hour)
        ]
        summary = summarize_hourly_window(block, 14, label)
        if summary:
            print_hourly_window(summary)
    print()

    if not daily.empty:
        recent = daily.tail(14).copy()
        print("recent_daily:")
        display = recent[[
            "Date",
            "Fact_MWh",
            "Base_MWh",
            "AI_MWh",
            "Base_Daily_MAPE",
            "AI_Daily_MAPE",
            "AI_Better",
            "Cloud_Avg",
            "Cloud_Max",
        ]].round(1)
        print(display.to_string(index=False))
        print()

    if not hourly.empty:
        end_date = pd.Timestamp(hourly["Date"].max())
        start_cutoff = end_date - pd.Timedelta(days=13)
        recent_hourly = hourly[
            pd.to_datetime(hourly["Date"]) >= start_cutoff
        ].copy()
        if not recent_hourly.empty:
            print("worst_ai_hours_last_14_days:")
            display_columns = [
                "Time",
                "Fact_MW",
                "Forecast_MW",
                "AI_Forecast_MW",
                "Base_Abs_Error_MW",
                "AI_Abs_Error_MW",
                "CloudCover",
                "PrecipProb",
            ]
            display_columns = [
                column for column in display_columns
                if column in recent_hourly.columns
            ]
            worst = recent_hourly.sort_values(
                "AI_Abs_Error_MW",
                ascending=False,
            ).head(10)
            display = worst[display_columns].copy()
            numeric_columns = display.select_dtypes(include=[np.number]).columns
            display[numeric_columns] = display[numeric_columns].round(2)
            print(display.to_string(index=False))
            print()

    shadow_daily = build_shadow_quality(df)
    if not shadow_daily.empty:
        print("shadow_quality:")
        for days in [7, 14, 30]:
            end_date = pd.Timestamp(shadow_daily["Date"].max())
            start_cutoff = end_date - pd.Timedelta(days=days - 1)
            window = shadow_daily[pd.to_datetime(shadow_daily["Date"]) >= start_cutoff]
            if window.empty:
                continue
            current = float(window["AI_Daily_MAPE"].mean())
            experiment = float(window["Shadow_Daily_MAPE"].mean())
            improvement = 100 * (current - experiment) / current if current else 0.0
            better = float(window["Shadow_Better_AI"].mean() * 100)
            print(
                f"  last_{days}_days: ai={current:.1f}% "
                f"shadow={experiment:.1f}% "
                f"improvement={improvement:+.1f}% "
                f"shadow_better_days={better:.0f}% "
                f"avg_factor={window['Shadow_Factor'].mean():.3f}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
