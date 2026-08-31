# SkyGrid Solar AI: прогнозування генерації СЕС НЗФ

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_svg)](https://solar-monitoring-system.streamlit.app/)

Streamlit-система моніторингу, контролю якості та погодинного прогнозування сонячної генерації для Нікопольського заводу феросплавів.

## Основні компоненти

- `collector.py` — production-пайплайн: факти з email, погода Visual Crossing, навчання корекції та запис прогнозу в Google Sheets.
- `app.py` — Streamlit-інтерфейс для прогнозу, якості AI, журналу контролю, метеоаналізу та плану.
- `scripts/forecast_quality_report.py` — read-only CLI-звіт якості прогнозу по Google Sheets CSV.
- `Dockerfile` — контейнерний запуск Streamlit UI для майбутнього production-хостингу з власним доменом.

## Перевірка якості прогнозу

```bash
python scripts/forecast_quality_report.py
```

Скрипт нічого не записує: він читає CSV-експорт Google Sheets і порівнює базовий прогноз із `AI_Forecast_MW` за погодинними MW-помилками та добовими MWh health-check метриками.

## Production deployment

Поточний публічний шлях залишається Streamlit Community Cloud. Репозиторій також підготовлено до контейнерного запуску Streamlit UI на Cloud Run, Render, Railway або VPS із власним доменом.

Деталі: [`docs/deployment.md`](docs/deployment.md).

## Operational checks

Якщо картка `Факт з початку місяця` виглядає заниженою, спочатку перевірте останній запуск `SkyGrid Auto Sync` у GitHub Actions. Логи мають містити імпорт листів/фактів з FusionSolar. Помилка Gmail IMAP `AUTHENTICATIONFAILED` означає, що треба оновити `EMAIL_USER` / `EMAIL_PASS` у GitHub Actions Secrets і вручну перезапустити workflow.

Картка факту рахується тільки з фактів, які вже потрапили в Google Sheets. Якщо імпорт пошти зупинився, значення може бути математично коректним для наявних даних, але неповним для реального місяця.

## Camino Planner через GitHub Pages

Статична PWA Camino Planner розміщена в `docs/camino/`.

Щоб опублікувати її через GitHub Pages:

1. Відкрийте `GitHub` → `Settings` → `Pages`.
2. У `Source` виберіть `Deploy from branch`.
3. Branch: `main`.
4. Folder: `/docs`.
5. Натисніть `Save`.

Після ввімкнення GitHub Pages Camino Planner буде доступний за адресою:

```text
https://sergejkolesnik.github.io/Solar-Monitoring-System/camino/
```

Supabase URL/key не зберігаються в коді. Введіть їх у вкладці `☁️ Синхр.` всередині Camino Planner.

## Розробники

- **С.І. Колесник** — ідея, автоматика та енергетична частина.
- **SkyGrid AI** — прогнозна логіка, інтерфейс і діагностика якості.
