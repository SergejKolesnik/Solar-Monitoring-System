# Production deployment notes

SkyGrid Solar AI currently runs on Streamlit Community Cloud. The repository is
now prepared for a second, production-style deployment path through a container.

The goal is to keep the existing Streamlit app and forecasting pipeline intact,
while making it possible to host the UI behind a normal domain such as
`skygrid.example.com`.

## Recommended first migration step

1. Keep Streamlit Community Cloud running as the fallback URL.
2. Deploy the same `app.py` container to a managed platform such as Google Cloud
   Run, Render, Railway, or a small VPS.
3. Configure a custom domain on that platform.
4. Move only the web UI first. Keep `collector.py` on GitHub Actions until the
   hosted app is stable.
5. Add monitoring/health checks before switching operators to the new URL.

This avoids changing the model, Google Sheets structure, email import, or
forecast calculation while we test the hosting layer.

## Runtime configuration

The app supports both Streamlit Secrets and environment variables. Streamlit
Secrets remain the preferred configuration for Streamlit Community Cloud.
Environment variables are intended for container hosting.

Required for the web UI:

- `GOOGLE_CREDENTIALS` - service account JSON as a single JSON string.
- `WEATHER_API_KEY` - Visual Crossing API key.

Optional for the web UI:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_SYNC_DAYS`

Required for the collector pipeline:

- `GOOGLE_CREDENTIALS`
- `WEATHER_API_KEY`
- `EMAIL_USER`
- `EMAIL_PASS`

Optional for the collector pipeline:

- `EMAIL_FOLDERS`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_SYNC_DAYS`

Do not commit `.env`, `.streamlit/secrets.toml`, service-account JSON files, API
keys, or exported production data.

## Local Docker check

Build:

```bash
docker build -t skygrid-solar-ai .
```

Run:

```bash
docker run --rm -p 8080:8080 \
  -e PORT=8080 \
  -e GOOGLE_CREDENTIALS="$GOOGLE_CREDENTIALS" \
  -e WEATHER_API_KEY="$WEATHER_API_KEY" \
  skygrid-solar-ai
```

Open:

```text
http://localhost:8080
```

Health endpoint:

```text
http://localhost:8080/_stcore/health
```

## Google Cloud Run outline

Cloud Run is a good first candidate because it supports containers, custom
domains, managed HTTPS, scaling, and environment variables.

High-level flow:

1. Create/select a Google Cloud project.
2. Enable Cloud Run and Artifact Registry.
3. Store secrets in Secret Manager or pass them as Cloud Run environment
   variables.
4. Build and deploy the container from this repository.
5. Attach a custom domain.
6. Keep the old Streamlit URL as fallback until operators confirm stability.

Do not move scheduled data collection to Cloud Run in the first phase. The
GitHub Actions collector is already isolated and stable enough to remain the
source of scheduled updates during the hosting migration.
