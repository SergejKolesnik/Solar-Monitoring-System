# Supabase schema

This folder contains the first safe database step for SkyGrid Solar AI.

The current production app still uses Google Sheets. The SQL schema here only prepares Postgres tables so data can later be duplicated into Supabase and compared against Google Sheets before switching the app read path.

## Tables

- `plant_capacity_history`: capacity changes over time.
- `solar_measurements`: hourly factual generation from inverter emails.
- `weather_forecasts`: hourly weather values from Visual Crossing or another provider.
- `generation_forecasts`: forecast snapshots for target hours and model versions.
- `forecast_quality_daily`: daily quality metrics for base forecast and AI forecast.

## Safety

All tables enable RLS and this schema intentionally creates no public `anon` or `authenticated` policies. Use server-side credentials only.

Do not paste service-role keys into source code or chat. Store Supabase secrets in Streamlit Secrets when the collector integration is added.

## Applying manually

1. Open Supabase Dashboard.
2. Go to SQL Editor.
3. Paste `schema.sql`.
4. Run it once.
5. Confirm the tables exist in Table Editor.

