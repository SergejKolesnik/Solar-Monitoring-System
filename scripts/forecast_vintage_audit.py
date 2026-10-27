"""Read-only backtest of next-day forecasts available by noon in Kyiv."""

from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


KYIV = ZoneInfo("Europe/Kyiv")
PAGE_SIZE = 1000
VINTAGE_FEATURE_COLUMNS = [
    "forecast_mw",
    "cloudcover",
    "temp",
    "windspeed",
    "precipprob",
    "capacity_mw",
    "hour",
    "month",
    "day_of_year",
]


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


def _candidate_metric(label: str, frame: pd.DataFrame, prediction_column: str) -> str:
    if frame.empty:
        return f"{label}: недостатньо збігів факт/прогноз"
    base_mae = (frame["forecast_mw"] - frame["fact_mw"]).abs().mean()
    model_mae = (frame[prediction_column] - frame["fact_mw"]).abs().mean()
    improvement = (1 - model_mae / base_mae) * 100 if base_mae > 0 else 0.0
    return (
        f"{label}: n={len(frame)}, база MAE={base_mae:.3f} МВт, "
        f"кандидат MAE={model_mae:.3f} МВт, зміна={improvement:+.1f}%"
    )


def _weather_source_metric(label: str, frame: pd.DataFrame) -> str:
    if frame.empty:
        return f"{label}: недостатньо спільних point-in-time годин"
    base_mae = (frame["provider_forecast_mw"] - frame["fact_mw"]).abs().mean()
    return f"{label}: n={len(frame)}, MAE={base_mae:.3f} МВт"


def _walk_forward_candidates(vintage: pd.DataFrame) -> pd.DataFrame:
    """Fit candidates only on earlier facts available at each issue timestamp."""

    feature_columns = [
        "forecast_mw",
        "cloudcover",
        "temp",
        "windspeed",
        "precipprob",
        "hour",
        "month",
        "day_of_year",
        "cloud_change_pct_points",
    ]
    data = vintage.dropna(
        subset=feature_columns
        + ["fact_mw", "fact_loaded_utc", "run_utc", "capacity_mw"]
    ).copy()
    data = data[(data["fact_mw"] > 0.05) & (data["forecast_mw"] > 0.05)]
    data = data[data["target_utc"].dt.tz_convert(KYIV).dt.hour.between(5, 20)]
    predictions = []

    for target_day in sorted(data["target_day"].unique()):
        test_rows = data[data["target_day"] == target_day].copy()
        if test_rows.empty:
            continue
        issue_run = test_rows["run_utc"].max()
        train_rows = data[
            (data["target_day"] < target_day)
            & (data["fact_loaded_utc"] <= issue_run)
        ].copy()
        if len(train_rows) < 120:
            continue

        estimators = {
            "walk_forward_hgb": HistGradientBoostingRegressor(
                max_iter=300,
                learning_rate=0.05,
                max_leaf_nodes=15,
                l2_regularization=0.1,
                early_stopping=True,
                random_state=42,
            ),
            "walk_forward_ridge": make_pipeline(
                StandardScaler(), Ridge(alpha=10.0)
            ),
        }
        for name, estimator in estimators.items():
            estimator.fit(
                train_rows[feature_columns].astype(float),
                train_rows["fact_mw"] - train_rows["forecast_mw"],
            )
            residual = estimator.predict(test_rows[feature_columns].astype(float))
            base = test_rows["forecast_mw"].to_numpy()
            capacity = test_rows["capacity_mw"].to_numpy()
            bound = base * 0.30
            predicted = (base + residual.clip(-bound, bound)).clip(0, capacity)
            result = test_rows[["target_utc", "target_day", "fact_mw", "forecast_mw", "ai_forecast_mw", "cloudcover"]].copy()
            result[name] = predicted
            result["walk_forward_train_rows"] = len(train_rows)
            predictions.append(result)

    if not predictions:
        return pd.DataFrame()
    combined = pd.concat(predictions, ignore_index=True)
    keys = ["target_utc", "target_day"]
    return combined.groupby(keys, as_index=False).first()


def _fixed_vintage_holdout(vintage: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Mirror the production 14-day split using issue-time weather vintages."""

    required = VINTAGE_FEATURE_COLUMNS + [
        "fact_mw",
        "fact_loaded_utc",
        "run_utc",
        "target_utc",
        "target_day",
        "capacity_mw",
        "forecast_mw",
        "ai_forecast_mw",
    ]
    data = vintage.dropna(subset=required).copy()
    data = data[
        (data["fact_mw"] > 0.05)
        & (data["forecast_mw"] > 0.05)
    ]
    if data.empty:
        return pd.DataFrame(), 0

    latest_day = data["target_day"].max()
    validation_start = latest_day - timedelta(days=13)
    validation = data[data["target_day"] >= validation_start].copy()
    training_cutoff = validation["run_utc"].min()
    training = data[
        (data["target_day"] < validation_start)
        & (data["fact_loaded_utc"] <= training_cutoff)
    ].copy()
    if len(training) < 120 or validation.empty:
        return pd.DataFrame(), len(training)

    validation["cloud_change_pct_points"] = validation[
        "cloud_change_pct_points"
    ].fillna(0)
    training["cloud_change_pct_points"] = training[
        "cloud_change_pct_points"
    ].fillna(0)
    feature_sets = {
        "vintage_holdout_hgb": VINTAGE_FEATURE_COLUMNS,
        "vintage_holdout_hgb_cloud_delta": VINTAGE_FEATURE_COLUMNS
        + ["cloud_change_pct_points"],
    }
    base = validation["forecast_mw"].to_numpy()
    capacity = validation["capacity_mw"].to_numpy()
    bound = base * 0.30
    for prediction_column, feature_columns in feature_sets.items():
        model = HistGradientBoostingRegressor(
            max_iter=300,
            learning_rate=0.05,
            max_leaf_nodes=15,
            l2_regularization=0.1,
            early_stopping=True,
            random_state=42,
        )
        model.fit(
            training[feature_columns].astype(float),
            training["fact_mw"] - training["forecast_mw"],
        )
        residual = model.predict(validation[feature_columns].astype(float))
        validation[prediction_column] = (base + residual.clip(-bound, bound)).clip(
            0, capacity
        )
    hours = validation["target_utc"].dt.tz_convert(KYIV).dt.hour
    night = (hours < 5) | (hours > 21)
    validation.loc[night, list(feature_sets)] = 0.0
    return validation, len(training)


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
            "select": "target_time,forecast_mw,ai_forecast_mw,capacity_mw,forecast_run_at,model_version,source",
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
            "select": "time,fact_mw,loaded_at",
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
            "select": "time,provider,rad,cloudcover,temp,windspeed,precipprob,loaded_at",
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
    if "source" not in forecasts.columns:
        forecasts["source"] = "legacy"
    legacy_forecast_count = int((forecasts["source"] != "collector_utc_v2").sum())
    forecasts = forecasts[forecasts["source"] == "collector_utc_v2"].copy()
    if forecasts.empty:
        return (
            "## Бектест прогнозу до 12:00 попереднього дня\n\n"
            f"Знайдено старих знімків: {legacy_forecast_count}, але їхні мітки часу "
            "непридатні для перевірки cutoff. Потрібно накопичити знімки з виправленим UTC-часом."
        )

    forecasts["run_utc"] = pd.to_datetime(forecasts["forecast_run_at"], utc=True, errors="coerce")
    forecasts["run_local"] = forecasts["run_utc"].dt.tz_convert(KYIV)
    facts["fact_mw"] = pd.to_numeric(facts["fact_mw"], errors="coerce")
    facts["fact_loaded_utc"] = pd.to_datetime(facts["loaded_at"], utc=True, errors="coerce")
    for column in ("forecast_mw", "ai_forecast_mw"):
        forecasts[column] = pd.to_numeric(forecasts[column], errors="coerce")
    forecasts["capacity_mw"] = pd.to_numeric(forecasts["capacity_mw"], errors="coerce")

    if not weather.empty:
        if "provider" not in weather.columns:
            weather["provider"] = "visual_crossing"
        weather["provider"] = weather["provider"].fillna("visual_crossing")
        weather["loaded_utc"] = pd.to_datetime(weather["loaded_at"], utc=True, errors="coerce")
        weather["rad"] = pd.to_numeric(weather.get("rad"), errors="coerce")
        weather["cloudcover"] = pd.to_numeric(weather["cloudcover"], errors="coerce")
        for column in ("temp", "windspeed", "precipprob"):
            weather[column] = pd.to_numeric(weather[column], errors="coerce")
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
        facts[["target_utc", "fact_mw", "fact_loaded_utc"]]
        .dropna()
        .drop_duplicates("target_utc"),
        on="target_utc",
        how="inner",
    )
    merged = merged[
        (merged["fact_mw"] > 0.05)
        & (merged["forecast_mw"] > 0.05)
        & (merged["target_utc"].dt.tz_convert(KYIV).dt.hour.between(5, 20))
    ].copy()
    lines.append(_metric_line("Усі продуктивні години", merged))

    if not weather.empty:
        matched_weather = weather.merge(
            selected_frame[["target_utc", "run_utc", "capacity_mw"]].drop_duplicates(),
            left_on=["target_utc", "loaded_utc"],
            right_on=["target_utc", "run_utc"],
            how="inner",
        ).merge(
            facts[["target_utc", "fact_mw"]].dropna().drop_duplicates("target_utc"),
            on="target_utc",
            how="inner",
        )
        matched_weather["provider_forecast_mw"] = (
            matched_weather["rad"]
            * 0.0114
            * matched_weather["capacity_mw"]
            / 12.5
        )
        matched_weather["local_hour"] = matched_weather[
            "target_utc"
        ].dt.tz_convert(KYIV).dt.hour
        matched_weather = matched_weather[
            (matched_weather["fact_mw"] > 0.05)
            & (matched_weather["provider_forecast_mw"] > 0.05)
            & matched_weather["local_hour"].between(5, 20)
        ]
        source_sets = {
            provider: group.set_index("target_utc")
            for provider, group in matched_weather.groupby("provider")
        }
        if "visual_crossing" in source_sets and "open_meteo" in source_sets:
            common_times = source_sets["visual_crossing"].index.intersection(
                source_sets["open_meteo"].index
            )
            vc_rows = source_sets["visual_crossing"].loc[common_times]
            om_rows = source_sets["open_meteo"].loc[common_times]
            lines.extend(
                [
                    "",
                    "### Погодні джерела на однакових прогнозних знімках до 12:00",
                    f"Спільні години з фактами: {len(common_times)}.",
                    _weather_source_metric("Visual Crossing", vc_rows),
                    _weather_source_metric("Open-Meteo", om_rows),
                    _weather_source_metric(
                        "Visual Crossing, хмарність ≥70%",
                        vc_rows[vc_rows["cloudcover"] >= 70],
                    ),
                    _weather_source_metric(
                        "Open-Meteo, хмарність ≥70%",
                        om_rows[om_rows["cloudcover"] >= 70],
                    ),
                ]
            )
        else:
            lines.extend(
                [
                    "",
                    "### Погодні джерела на однакових прогнозних знімках до 12:00",
                    "Порівняння почнеться після появи vintage-знімків обох джерел.",
                ]
            )

    if not weather.empty and not merged.empty:
        # Keep the existing model diagnostic tied to its production source.
        # Open-Meteo rows are evaluated separately below to avoid duplicate joins.
        weather = weather[weather["provider"] == "visual_crossing"].copy()
        weather = weather.sort_values("target_utc").copy()
        weather["cloud_change_pct_points"] = weather.groupby(
            ["target_day", "loaded_utc"]
        )["cloudcover"].diff().abs()
        merged = merged.merge(
            weather[
                [
                    "target_utc",
                    "loaded_utc",
                    "cloudcover",
                    "temp",
                    "windspeed",
                    "precipprob",
                    "cloud_change_pct_points",
                ]
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
        merged["hour"] = merged["target_utc"].dt.tz_convert(KYIV).dt.hour
        merged["month"] = merged["target_utc"].dt.tz_convert(KYIV).dt.month
        merged["day_of_year"] = merged["target_utc"].dt.tz_convert(KYIV).dt.dayofyear
        merged["capacity_mw"] = pd.to_numeric(merged["capacity_mw"], errors="coerce")
        candidate_rows = _walk_forward_candidates(merged)
        if candidate_rows.empty:
            lines.append("Walk-forward кандидатам не вистачило історичних point-in-time фактів.")
        else:
            candidate_rows["target_month"] = pd.to_datetime(
                candidate_rows["target_day"]
            ).dt.strftime("%Y-%m")
            recent_cutoff = candidate_rows["target_day"].max() - timedelta(days=13)
            recent_rows = candidate_rows[candidate_rows["target_day"] >= recent_cutoff]
            lines.extend(
                [
                    "",
                    "### Офлайн walk-forward кандидати (робочий прогноз не змінюється)",
                    f"Дати тесту: {candidate_rows['target_day'].nunique()}; "
                    f"погодинних фактів: {len(candidate_rows)}; "
                    f"мінімум навчальних рядків: {candidate_rows['walk_forward_train_rows'].min()}.",
                    _candidate_metric(
                        "Поточний збережений AI", candidate_rows, "ai_forecast_mw"
                    ),
                    _candidate_metric(
                        "HistGradientBoosting", candidate_rows, "walk_forward_hgb"
                    ),
                    _candidate_metric(
                        "Ridge", candidate_rows, "walk_forward_ridge"
                    ),
                    _candidate_metric(
                        "HGB на хмарності ≥70%",
                        candidate_rows[candidate_rows["cloudcover"] >= 70],
                        "walk_forward_hgb",
                    ),
                    _candidate_metric(
                        "Ridge на хмарності ≥70%",
                        candidate_rows[candidate_rows["cloudcover"] >= 70],
                        "walk_forward_ridge",
                    ),
                    "",
                    f"Останні 14 календарних днів: {recent_rows['target_day'].nunique()} дат, "
                    f"{len(recent_rows)} годин.",
                    _candidate_metric(
                        "Збережений AI, останні 14 днів",
                        recent_rows,
                        "ai_forecast_mw",
                    ),
                    _candidate_metric(
                        "HGB, останні 14 днів",
                        recent_rows,
                        "walk_forward_hgb",
                    ),
                    _candidate_metric(
                        "HGB на хмарності ≥70%, останні 14 днів",
                        recent_rows[recent_rows["cloudcover"] >= 70],
                        "walk_forward_hgb",
                    ),
                ]
            )
            for month, month_rows in candidate_rows.groupby("target_month"):
                lines.append(
                    f"{month}: "
                    + _candidate_metric(
                        "збережений AI", month_rows, "ai_forecast_mw"
                    )
                )
                lines.append(
                    f"{month}: "
                    + _candidate_metric("HGB", month_rows, "walk_forward_hgb")
                )
        holdout_rows, holdout_train_count = _fixed_vintage_holdout(merged)
        lines.extend(
            [
                "",
                "### Фіксований 14-денний vintage holdout (ознаки production-моделі)",
            ]
        )
        if holdout_rows.empty:
            lines.append(
                f"Недостатньо point-in-time даних: train={holdout_train_count}; "
                "потрібно щонайменше 120 рядків навчання."
            )
        else:
            lines.append(
                f"train={holdout_train_count}; validation={len(holdout_rows)}; "
                f"дати={holdout_rows['target_day'].nunique()}."
            )
            lines.append(
                _candidate_metric(
                    "HGB на збережених прогнозних ознаках",
                    holdout_rows,
                    "vintage_holdout_hgb",
                )
            )
            holdout_cloudy = holdout_rows[holdout_rows["cloudcover"] >= 70]
            lines.append(
                _candidate_metric(
                    "HGB на хмарності ≥70%",
                    holdout_cloudy,
                    "vintage_holdout_hgb",
                )
            )
            lines.append(
                _candidate_metric(
                    "HGB + зміна хмарності",
                    holdout_rows,
                    "vintage_holdout_hgb_cloud_delta",
                )
            )
            lines.append(
                _candidate_metric(
                    "HGB + зміна хмарності на хмарності ≥70%",
                    holdout_cloudy,
                    "vintage_holdout_hgb_cloud_delta",
                )
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
