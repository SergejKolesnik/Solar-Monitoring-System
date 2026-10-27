"""Read-only backtest of next-day forecasts available by noon in Kyiv."""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests


KYIV = ZoneInfo("Europe/Kyiv")
PAGE_SIZE = 1000


def _get_all_rows(session: requests.Session, base_url: str, table: str, params: dict) -> list[dict]:
    """Fetch a bounded PostgREST result using stable range pagination."""

    rows: list[dict] = []
    offset = 0
    while True:
        response = session.get(
            f"{base_url}/rest/v1/{table}",
            params=params,
            headers={"Range-Unit": "items", "Range": f"{offset}-{offset + PAGE_SIZE - 1}"},
            timeout=30,
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list):
            raise ValueError(f"Unexpected response from {table}")
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def _read_config() -> tuple[str, str, int]:
    """Read server-side Supabase configuration without printing credentials."""

    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    days = int(os.getenv("SUPABASE_SYNC_DAYS", "40"))
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
    if days < 2 or days > 365:
        raise ValueError("SUPABASE_SYNC_DAYS must be between 2 and 365")
    return url, key, days


def _metric_line(label: str, frame: pd.DataFrame) -> str:
    if frame.empty:
        return f"{label}: недостатньо збігів факт/прогноз"
    base_mae = (frame["forecast_mw"] - frame["fact_mw"]).abs().mean()
    ai_mae = (frame["ai_forecast_mw"] - frame["fact_mw"]).abs().mean()
    improvement = (1 - ai_mae / base_mae) * 100 if base_mae > 0 else 0.0
    return (
        f"{label}: n={len(frame)}, база MAE={base_mae:.3f} МВт, "
        f"AI MAE={ai_mae:.3f} МВт, зміна={improvement:+.1f}%"
    )


def build_report(now: datetime | None = None) -> str:
    """Evaluate the latest forecast issued by 12:00 Kyiv time on the prior day."""

    url, key, sync_days = _read_config()
    now = now or datetime.now(KYIV)
    if now.tzinfo is None:
        now = now.replace(tzinfo=KYIV)
    now = now.astimezone(KYIV)
    first_target_day = now.date() - timedelta(days=sync_days)
    last_target_day = now.date() - timedelta(days=1)
    query_start = datetime.combine(first_target_day, time.min, tzinfo=KYIV).astimezone(
        ZoneInfo("UTC")
    )
    query_end = datetime.combine(now.date(), time.min, tzinfo=KYIV).astimezone(
        ZoneInfo("UTC")
    )

    session = requests.Session()
    session.headers.update(
        {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        }
    )

    forecast_rows = _get_all_rows(
        session,
        url,
        "generation_forecasts",
        {
            "select": "target_time,forecast_mw,ai_forecast_mw,forecast_run_at,model_version",
            "target_time": f"gte.{query_start.isoformat()}",
            "and": f"(target_time.lt.{query_end.isoformat()})",
            "order": "target_time.asc,forecast_run_at.asc",
        },
    )
    fact_rows = _get_all_rows(
        session,
        url,
        "solar_measurements",
        {
            "select": "time,fact_mw",
            "time": f"gte.{query_start.isoformat()}",
            "and": f"(time.lt.{query_end.isoformat()})",
            "order": "time.asc",
        },
    )
    weather_rows = _get_all_rows(
        session,
        url,
        "weather_forecasts",
        {
            "select": "time,cloudcover,loaded_at",
            "time": f"gte.{query_start.isoformat()}",
            "and": f"(time.lt.{query_end.isoformat()})",
            "order": "time.asc,loaded_at.asc",
        },
    )

    if not forecast_rows or not fact_rows:
        return (
            "## Бектест прогнозу до 12:00 попереднього дня\n\n"
            f"Недостатньо історії у Supabase: forecasts={len(forecast_rows)}, "
            f"facts={len(fact_rows)}. Перевірте, чи shadow sync увімкнений."
        )

    forecasts = pd.DataFrame(forecast_rows)
    facts = pd.DataFrame(fact_rows)
    weather = pd.DataFrame(weather_rows)
    for frame, column in ((forecasts, "target_time"), (facts, "time"), (weather, "time")):
        if not frame.empty:
            frame["target_utc"] = pd.to_datetime(frame[column], utc=True, errors="coerce")
            frame["target_day"] = frame["target_utc"].dt.tz_convert(KYIV).dt.date
    forecasts["run_utc"] = pd.to_datetime(forecasts["forecast_run_at"], utc=True, errors="coerce")
    forecasts["run_local"] = forecasts["run_utc"].dt.tz_convert(KYIV)
    facts["fact_mw"] = pd.to_numeric(facts["fact_mw"], errors="coerce")
    for column in ("forecast_mw", "ai_forecast_mw"):
        forecasts[column] = pd.to_numeric(forecasts[column], errors="coerce")

    if not weather.empty:
        weather["loaded_utc"] = pd.to_datetime(weather["loaded_at"], utc=True, errors="coerce")
        weather["cloudcover"] = pd.to_numeric(weather["cloudcover"], errors="coerce")
        weather = weather.dropna(subset=["target_utc", "loaded_utc"])

    target_days = sorted(
        day
        for day in facts["target_day"].dropna().unique()
        if first_target_day <= day <= last_target_day
    )
    selected = []
    coverage = []
    for target_day in target_days:
        issue_date = target_day - timedelta(days=1)
        cutoff = datetime.combine(issue_date, time(12), tzinfo=KYIV)
        day_rows = forecasts[
            (forecasts["target_day"] == target_day)
            & (forecasts["run_local"] <= cutoff)
            & (forecasts["run_local"].dt.date == issue_date)
        ]
        if day_rows.empty:
            coverage.append((target_day, None, 0))
            continue
        selected_run = day_rows["run_utc"].max()
        run_rows = day_rows[day_rows["run_utc"] == selected_run].copy()
        coverage.append((target_day, selected_run, len(run_rows)))
        selected.append(run_rows)

    lines = [
        "## Бектест прогнозу до 12:00 попереднього дня",
        "",
        f"Період фактів: {first_target_day} — {last_target_day}; "
        f"днів із фактами: {len(target_days)}.",
        f"Знімок: останній запуск попереднього дня не пізніше 12:00 Kyiv; "
        f"днів із доступним знімком: {sum(run is not None for _, run, _ in coverage)}.",
        "",
    ]
    if not selected:
        lines.append("У межах доступного періоду немає знімків із потрібним часом випуску.")
        return "\n".join(lines)

    selected_frame = pd.concat(selected, ignore_index=True)
    selected_runs = selected_frame[["target_day", "run_local"]].drop_duplicates()
    issue_hours = selected_runs["run_local"].dt.strftime("%H:%M")
    issue_hour_median = selected_runs["run_local"].dt.hour.median()
    merged = selected_frame.merge(
        facts[["target_utc", "fact_mw"]].dropna().drop_duplicates("target_utc"),
        on="target_utc",
        how="inner",
    )
    merged = merged[
        (merged["fact_mw"] > 0.05)
        & (merged["forecast_mw"] > 0.05)
        & (merged["target_utc"].dt.tz_convert(KYIV).dt.hour.between(5, 20))
    ].copy()
    lines.append(_metric_line("Усі продуктивні години", merged))

    if not weather.empty and not merged.empty:
        weather = weather.sort_values("target_utc").copy()
        weather["cloud_change_pct_points"] = weather.groupby(
            ["target_day", "loaded_utc"]
        )["cloudcover"].diff().abs()
        merged = merged.merge(
            weather[
                ["target_utc", "loaded_utc", "cloudcover", "cloud_change_pct_points"]
            ].drop_duplicates(
                ["target_utc", "loaded_utc"]
            ),
            left_on=["target_utc", "run_utc"],
            right_on=["target_utc", "loaded_utc"],
            how="left",
        )
        cloudy = merged[merged["cloudcover"] >= 70]
        mixed = merged[merged["cloudcover"].between(40, 69, inclusive="both")]
        clear = merged[merged["cloudcover"] < 40]
        rapidly_changing = merged[merged["cloud_change_pct_points"] >= 25]
        moderately_changing = merged[
            merged["cloud_change_pct_points"].between(10, 24.999, inclusive="both")
        ]
        relatively_stable = merged[merged["cloud_change_pct_points"] < 10]
        lines.extend(
            [
                _metric_line("Хмарність ≥70%", cloudy),
                _metric_line("Хмарність 40–69%", mixed),
                _metric_line("Хмарність <40%", clear),
                _metric_line("Зміна хмарності ≥25 п.п./год", rapidly_changing),
                _metric_line("Зміна хмарності 10–24 п.п./год", moderately_changing),
                _metric_line("Зміна хмарності <10 п.п./год", relatively_stable),
                f"Годин без погодного знімка тієї самої версії: {merged['cloudcover'].isna().sum()}.",
            ]
        )
    else:
        lines.append("Погодинний погодний знімок для групування за хмарністю відсутній.")

    lines.extend(
        [
            "",
            "Показник зміни: додатне значення означає нижчу MAE моделі відносно бази; "
            "вибірка містить лише валідні денні факти.",
            f"Час випуску вибраних знімків: {issue_hours.min()}–{issue_hours.max()} Kyiv; "
            f"медіана години: {issue_hour_median:.1f}.",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    report = build_report()
    print(report)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary_file:
            summary_file.write(report + "\n")
