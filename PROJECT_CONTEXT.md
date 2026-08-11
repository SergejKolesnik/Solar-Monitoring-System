# SkyGrid Solar AI — Project Context

Last audited: 2026-08-11

Repository: `C:\Users\User\Documents\Projects\Solar-Monitoring-System`

GitHub: `https://github.com/SergejKolesnik/Solar-Monitoring-System`

## Мета проєкту

SkyGrid Solar AI — система моніторингу, аналізу та погодинного прогнозування сонячної генерації СЕС Нікопольського феросплавного заводу. Основний продукт — Streamlit-вебзастосунок із прогнозом, фактичною генерацією, оцінкою якості, журналом контролю, метеоаналізом і плановими показниками.

## Користувач / бізнес-задача

- Оперативно бачити погодинну фактичну та прогнозовану генерацію СЕС.
- Порівнювати базовий і AI-скоригований прогнози.
- Контролювати свіжість і якість фактів, погоди та прогнозів.
- Використовувати встановлену потужність СЕС і планові дані у розрахунках.
- Надавати прогноз через вебінтерфейс без запуску навчання моделі під час відкриття сторінки.

Точний перелік production-користувачів, SLA та формальний бізнес-власник у репозиторії **не підтверджені**.

## Поточна архітектура

1. GitHub Actions періодично запускає `collector.py`.
2. Collector читає основну Google Sheet і налаштування потужності.
3. Фактична генерація імпортується з Excel-вкладень у пошті через IMAP.
4. Погодні та базові прогнозні дані оновлюються з Visual Crossing.
5. Collector рахує помилки, навчає модель корекції та записує `AI_Forecast_MW` назад у Google Sheets.
6. Після успішного основного циклу дані опціонально копіюються до Supabase у shadow-режимі.
7. `app.py` читає збережені дані з Google Sheets, отримує актуальну погоду і відображає Streamlit UI. Вебзастосунок не навчає production-модель під час відкриття сторінки.

## Основні модулі

| Файл / каталог | Роль |
|---|---|
| `app.py` | Streamlit entry point; завантажує Google Sheets, погоду і план, керує вкладками та відображенням прогнозу. |
| `collector.py` | Production pipeline: факти з email, погода, базовий прогноз, перевірки якості, навчання корекції, Google Sheets і shadow sync у Supabase. |
| `weather_service.py` | Клієнти Visual Crossing та Open-Meteo, базова формула прогнозу і розрахунок site coefficient. |
| `dashboard_components.py` | Основний графік, метрики, weather strip і індикатор довіри до прогнозу. |
| `ui_components.py` | Вкладки якості AI, даних, журналу, метеоаналізу й плану; read-only діагностика та shadow-експеримент. |
| `model_engine.py` | Окремий старіший/аналітичний шлях з `GradientBoostingRegressor`; його використання production-пайплайном не підтверджено. |
| `test_lab.py` | Ручний Streamlit-полігон для перевірки візуалізації; не автоматичний тест. |
| `supabase/` | Solar-specific SQL-схема та інструкція для shadow-сховища. |
| `.github/workflows/` | Scheduled collector, ручний fix workflow і keep-alive для Streamlit. |
| `docs/camino/` | Окремий статичний Camino Planner PWA; не частина Solar runtime. |

## Джерела метеоданих

- **Visual Crossing** — основне джерело прогнозу погоди для координат `47.631494, 34.348690`. Використовуються температура, сонячна радіація, хмарність, швидкість вітру та ймовірність опадів. Потребує `WEATHER_API_KEY`.
- **Open-Meteo** — додаткове безключове джерело для порівняння та метеоаналізу.
- Базовий прогноз у `weather_service.py` використовує формулу `Rad * 0.0114 * (capacity_mw / 12.5) * kef`. Production collector також формує `Forecast_MW` із погодних даних.

Інші production-джерела метеоданих кодом **не підтверджені**.

## Дані сонячної генерації

- Факти імпортуються `collector.py` з Excel-вкладень у поштових папках, заданих `EMAIL_FOLDERS`; типове значення: `FusionSolar`, `INBOX`, `[Gmail]/All Mail`.
- Значення з вкладень перетворюються з кВт·год у МВт·год/погодинне MW-представлення відповідно до чинної логіки `parse_kwh_value()` та записуються як `Fact_MW`.
- Основні колонки включають `Time`, `Forecast_MW`, погодні поля, `Fact_MW`, `Capacity_MW`, `AI_Forecast_MW` і поля помилок.
- Поточна встановлена потужність зберігається в аркуші `Settings` Google Sheets під ключем `Capacity_MW`; fallback — `12.5` МВт.

README посилається на `solar_ai_base.csv`, але такого tracked-файлу в поточному репозиторії немає. Актуальним operational-сховищем за кодом є Google Sheets, а не локальна CSV-база.

## Логіка прогнозування / AI

- Базовий прогноз ґрунтується на сонячній радіації та масштабується до потужності СЕС.
- Production-модель у `collector.py` — `HistGradientBoostingRegressor`.
- Ціль моделі: `Forecast_Error_MW = Fact_MW - Forecast_MW`.
- AI-прогноз: `AI_Forecast_MW = Forecast_MW + predicted_error`.
- Навчання потребує щонайменше 20 валідних рядків із позитивними фактом і базовим прогнозом; інакше AI-прогноз дорівнює базовому.
- Корекція обмежується ±30% базового прогнозу, результат — діапазоном від 0 до потужності СЕС; нічні години обнуляються.
- Collector навчає модель у часовому вікні або коли прогноз на поточний день відсутній, після чого зберігає прогноз у Google Sheets.
- Поточний training MAE обчислюється на навчальних даних. Chronological holdout/backtest для production-моделі не реалізовано.
- `ui_components.py` містить read-only shadow-експеримент корекції за bucket хмарності. Він лише відображає порівняння і не змінює operational `AI_Forecast_MW`.

## Streamlit UI

- Entry point: `app.py`.
- Основні вкладки: `Прогноз`, `Якість ШІ`, `Журнал`, `Дані`, `Метеоаналіз`, `План`.
- UI показує основний погодинний графік, метрики, погоду, довіру до прогнозу, діагностику якості та Excel-експорт.
- `dashboard_components.py` і `ui_components.py` містять основні presentation-компоненти.
- Тема визначена в `.streamlit/config.toml`.
- Доступ до Google Sheets та Visual Crossing у Streamlit виконується через `st.secrets`.

## Зберігання історичних даних

- **Google Sheets** — поточне operational source of truth для історії, прогнозів, фактів, помилок і налаштувань.
- **Supabase** — опціональна server-side shadow-копія. `collector.py` синхронізує capacity, measurements, weather, forecasts і daily quality, якщо задані `SUPABASE_URL` та `SUPABASE_SERVICE_ROLE_KEY`.
- SQL у `supabase/schema.sql` вмикає RLS і не створює публічних policies для Solar-таблиць.
- Локальна CSV-база, заявлена README, у поточному checkout відсутня.

## Deployment

- Streamlit badge і README ведуть на `https://solar-monitoring-system.streamlit.app/`.
- `.github/workflows/auto_sync.yml` запускає `collector.py` за розкладом і вручну з Python 3.9 та GitHub Secrets.
- `.github/workflows/keep_alive.yml` періодично пінгує Streamlit URL.
- `.github/workflows/fix_base.yml` є ручним one-time workflow.
- Camino Planner публікується окремо через GitHub Pages із `docs/camino/`.

Фактичні налаштування Streamlit Cloud поза репозиторієм, активність deployment і поточний стан GitHub Secrets локально **не підтверджені**.

## Camino Planner у цьому репозиторії

`docs/camino/` — автономний статичний travel-planner/PWA з `localStorage`, `IndexedDB`, service worker і опціональною Supabase-синхронізацією. Git-історія показує, що його додано commit `3ac5477` (`Publish Camino Planner to GitHub Pages`) для публікації через Pages цього репозиторію.

У Python-коді SkyGrid не знайдено імпортів або runtime-зв’язків із Camino. Тому Camino слід вважати **окремим стороннім/історично співрозміщеним компонентом**, а не частиною основної Solar-архітектури. Причина вибору саме цього репозиторію як хостингу, крім використання GitHub Pages, **не підтверджена**.

Не плутати:

- `supabase/schema.sql` — закрита shadow-схема SkyGrid Solar AI;
- SQL та Supabase-інструкції в `docs/camino/README.md` — окрема схема Camino PWA з іншою моделлю доступу.

## Відомі обмеження

- Production-запуск залежить від зовнішніх API, Google Sheets, email та секретів.
- Без достатньої історії модель переходить на базовий прогноз.
- Production-модель не зберігається як artifact, а навчається під час collector run.
- Оцінка production-моделі використовує training MAE; незалежної часової валідації немає.
- Автоматичного unit/integration test suite не знайдено.
- `test_lab.py` потребує Streamlit secret і мережі та є ручним UI-полігоном.
- Поведінка при частково доступних/застарілих зовнішніх даних покривається діагностикою, але не автоматичними тестами.

## Поточні проблеми / технічний борг

1. README починається з Camino і змішує два незалежні продукти; Solar-проєкт має бути описаний першим.
2. README містить посилання на відсутній `solar_ai_base.csv` і згадку про «нейронні мережі», тоді як підтверджені моделі — gradient boosting.
3. `fix_base.yml` запускає відсутній у репозиторії `fix_base.py`, тому workflow виглядає непрацездатним.
4. URL у `keep_alive.yml` (`pd2b4edrjntm8tyeulappbo.streamlit.app`) не збігається з URL у README (`solar-monitoring-system.streamlit.app`); правильний production URL не підтверджено.
5. `requirements.txt` не містить явної залежності `streamlit`, хоча основний застосунок її імпортує.
6. Немає автоматичних тестів і CI-перевірки синтаксису/тестів.
7. `model_engine.py` дублює окремий модельний шлях і може створювати плутанину щодо production-моделі.
8. `app.py`, `dashboard_components.py` та особливо `ui_components.py` великі й поєднують багато UI-відповідальностей; рефакторинг не входив у цей аудит.

## Наступні пріоритети

1. Виправити README: поставити SkyGrid першим, відокремити Camino, прибрати або актуалізувати CSV-посилання й опис моделі.
2. Перевірити production Streamlit URL та узгодити `keep_alive.yml`.
3. Вирішити долю `fix_base.yml`: повернути підтверджений script або видалити/архівувати workflow окремим погодженим завданням.
4. Додати мінімальні автоматичні тести для чистих функцій даних і прогнозування та CI syntax/test check.
5. Додати chronological holdout/backtest для порівняння baseline та AI до будь-якого просування нової моделі.
6. Після достатнього періоду спостереження окремо оцінити shadow-експеримент; не змінювати operational прогноз без доказів.
7. Розглянути перенесення Camino до окремого репозиторію лише як окреме, явно погоджене рішення.

## Правила продовження роботи з іншого ПК

1. Використовувати канонічний clone цього GitHub-репозиторію, а не старі ZIP/архівні копії.
2. Перед роботою перевірити branch, `git status`, remote і останній commit.
3. Синхронізуватися через GitHub; не копіювати файли між ПК вручну поверх checkout.
4. Не переносити secrets через Git. Налаштовувати їх окремо в GitHub Actions/Streamlit Secrets на відповідному середовищі.
5. Не починати роботу поверх невідомих локальних змін; спочатку з’ясувати їх походження.
6. Після змін виконати доступні тести, syntax checks, `git diff --check` і переглянути `git status`.
7. Оновлювати цей файл, якщо змінюються architecture, data flow, deployment або пріоритети.

## Current state

Стан на 2026-08-11 перед додаванням контекстних файлів:

- Branch: `main`.
- Tracking: `origin/main`.
- Remote: `https://github.com/SergejKolesnik/Solar-Monitoring-System.git` (fetch/push).
- Working tree: clean.
- HEAD: `b037767 Guard shadow experiment against data errors`.
- Основний Streamlit entry point: `app.py`.
- Production collector: `collector.py`.
- Google Sheets залишається operational source of truth.
- Supabase використовується як опціональний shadow sync.
- conventional automated tests: не знайдено.
- Camino Planner: присутній у `docs/camino/` як окремий GitHub Pages PWA.

## Architectural decisions

- 2026-08-11: зафіксовано, що Solar Python/Streamlit application є основним продуктом, а `docs/camino/` — окремим co-located компонентом без runtime-зв’язку.
- 2026-08-11: Google Sheets задокументовано як чинне operational-сховище; Supabase — як shadow-копію до окремого рішення про міграцію.
- 2026-08-11: production-моделлю вважається шлях `collector.py` з `HistGradientBoostingRegressor`; `model_engine.py` не вважається production без додаткового підтвердження.
