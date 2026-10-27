# SkyGrid Solar AI — Project Context

Last audited: 2026-08-14

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
| `data_quality.py` | Єдині правила відбору валідного факту, нормалізація київського часу та детермінована обробка DST. |
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
- Training MAE лишається діагностикою, але допуск моделі визначає окремий chronological holdout.
- Перед production-навчанням кандидат проходить chronological holdout за останні 14 днів (або останні 20 рядків при короткому вікні). Якщо його MAE не краща за базу щонайменше на 2%, collector записує базовий прогноз замість AI-корекції.
- `ui_components.py` містить read-only shadow-експеримент корекції за bucket хмарності. Він лише відображає порівняння і не змінює operational `AI_Forecast_MW`.
- `scripts/forecast_quality_report.py` дає read-only CLI-звіт якості по Google Sheets CSV: погодинні MAE/RMSE/bias у МВт, розбивку по ранку/піку/вечору, найгірші години, добову MAPE як контрольний health-check і окрему оцінку shadow-корекції.

## Streamlit UI

- Entry point: `app.py`.
- Основні верхні вкладки: `Огляд`, `План`, `Погода`, `Якість ШІ`.
- `Огляд` — прогноз на завтра, пік, розбіжність Visual Crossing/Open-Meteo, індикатор довіри й погодинний графік. `Погода` містить короткий прогноз, а детальне порівняння джерел і погода сьогодні доступні в закритих розгортаннях. Детальна історія помилок також згорнута в `Якість ШІ`.
- Технічні сторінки `Журнал` і `Дані` прибрані з основної навігації, їхні функції/код збережені для майбутнього внутрішнього доступу.
- `dashboard_components.py` і `ui_components.py` містять основні presentation-компоненти.
- Тема визначена в `.streamlit/config.toml`.
- Доступ до Google Sheets та Visual Crossing у Streamlit виконується через `st.secrets`.

## Зберігання історичних даних

- **Google Sheets** — поточне operational source of truth для історії, прогнозів, фактів, помилок і налаштувань.
- **Supabase** — опціональна server-side shadow-копія. `collector.py` синхронізує capacity, measurements, weather, forecasts і daily quality, якщо задані `SUPABASE_URL` та `SUPABASE_SERVICE_ROLE_KEY`. Планується зберігати знімки Visual Crossing та Open-Meteo окремо з часом UTC для ретроспективного порівняння.
- SQL у `supabase/schema.sql` вмикає RLS і не створює публічних policies для Solar-таблиць.
- Локальна CSV-база, заявлена README, у поточному checkout відсутня.
- Collector записує основну Google Sheet через повторно використовуваний `_collector_staging`: staging повністю записується і валідується, після чого values атомарно переносяться в чинний production worksheet одним `spreadsheets.batchUpdate`. Production `sheetId`, title, index, formatting, protected ranges і charts не замінюються. Supabase sync виконується лише після успішної production readback validation.

## Deployment

- Streamlit badge і README ведуть на чинний `https://pd2b4edrjntm8tyeulappbo.streamlit.app/`.
- `.github/workflows/auto_sync.yml` запускає `collector.py` за розкладом і вручну з Python 3.9 та GitHub Secrets.
- `.github/workflows/keep_alive.yml` періодично пінгує Streamlit URL.
- `.github/workflows/fix_base.yml` є ручним one-time workflow.
- Camino Planner публікується окремо через GitHub Pages із `docs/camino/`.
- `Dockerfile` і `docs/deployment.md` додають другий, production-style шлях для запуску Streamlit UI як контейнера на Cloud Run/Render/Railway/VPS із власним доменом. Перший етап не переносить `collector.py` з GitHub Actions і не змінює модель або Google Sheets data flow.
- `runtime_config.py` дозволяє UI читати `GOOGLE_CREDENTIALS` і `WEATHER_API_KEY` як зі Streamlit Secrets, так і з environment variables для контейнерного хостингу.
- `usage_analytics.py` optionally sends one anonymous PostHog page-view event tagged `skygrid-solar`; tracking remains disabled when `POSTHOG_API_KEY` is absent.

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
4. Фактичний Streamlit Cloud URL — `pd2b4edrjntm8tyeulappbo.streamlit.app`; README і `keep_alive.yml` мають залишатися узгодженими з ним.
5. `requirements.txt` не містить явної залежності `streamlit`, хоча основний застосунок її імпортує.
6. Автоматичні unit-тести є, але окремого обов'язкового CI workflow для повного test suite ще немає.
7. `model_engine.py` дублює окремий модельний шлях і може створювати плутанину щодо production-моделі.
8. `app.py`, `dashboard_components.py` та особливо `ui_components.py` великі й поєднують багато UI-відповідальностей; рефакторинг не входив у цей аудит.

## Operational audit 2026-08-31

- GitHub Actions `SkyGrid Auto Sync` продовжував завершуватися зеленим статусом, але в логах були `AUTHENTICATIONFAILED` для Gmail IMAP.
- Через це нові Excel-звіти з FusionSolar не імпортувалися, а Google Sheets містила факти лише до `2026-08-25 19:00`.
- Картка `Факт з початку місяця` рахувала суму коректно по наявних у Google Sheets фактах: `2069.523` МВт·год за серпень, але ця сума неповна через зупинку імпорту фактів.
- `collector.py` змінено так, щоб відсутні або невалідні `EMAIL_USER` / `EMAIL_PASS` зупиняли pipeline помилкою, а не маскувалися під `Нових фактів не знайдено`.
- `Keep Site Awake` пінгує Streamlit URL, але приватний/авторизований Streamlit endpoint повертає `303` на auth; такий ping не є надійним доказом, що застосунок прокинувся.

## Наступні пріоритети

1. **Попередні vintage-метрики є лише орієнтовними.** У старій версії collector UTC-час запуска записувався як локальний час, через що знімки могли виглядати на 3 години ранішими. Значення за 41 датою, walk-forward і 14-денний holdout не використовувати для висновків про cutoff до 12:00 або зміни моделі.
2. **Збір обох погодних джерел і виправлений час випуску — поточний крок.** PR додає Open-Meteo у наявну shadow-таблицю окремим provider та зберігає час кожного знімка в UTC; production forecast, Google Sheet і навчання не змінюються. Backtest відбиратиме лише новий маркер джерела `collector_utc_v2`, ігноруючи старі некоректно датовані записи.
3. **Після збирання достатньої історії** порівняти Visual Crossing та Open-Meteo на спільних продуктивних годинах прогнозу на завтра, виданих до 12:00 Kyiv, а потім повторити перевірку AI-кандидатів. Орієнтир для першого стабільного огляду — близько 40 днів після запуску коректного збирання; до того не змінювати робочу модель.
4. **Навігацію й оглядовий екран перебудовано в коді.** 4 вкладки: `Огляд`, `План`, `Погода`, `Якість ШІ`. Огляд додає розбіжність двох погодних джерел за однаковими годинами завтра; довгі метеографіки та детальна якість згорнуті. `Журнал` і `Дані` прибрані з верхньої навігації, але функції залишені. Чекає review/PR перед production.
5. Після стабільної перевірки показати в UI явний режим активної моделі, дату перевірки, похибку проти бази та причину fallback.
6. Інші попередні пріоритети технічного боргу (README, CI, fix_base.yml, Camino) залишаються окремими від поточної задачі якості прогнозу.

## Правила продовження роботи з іншого ПК

1. Використовувати канонічний clone цього GitHub-репозиторію, а не старі ZIP/архівні копії.
2. Перед роботою перевірити branch, `git status`, remote і останній commit.
3. Синхронізуватися через GitHub; не копіювати файли між ПК вручну поверх checkout.
4. Не переносити secrets через Git. Налаштовувати їх окремо в GitHub Actions/Streamlit Secrets на відповідному середовищі.
5. Не починати роботу поверх невідомих локальних змін; спочатку з’ясувати їх походження.
6. Після змін виконати доступні тести, syntax checks, `git diff --check` і переглянути `git status`.
7. Оновлювати цей файл, якщо змінюються architecture, data flow, deployment або пріоритети.

## Current state

### Detailed weather tab (2026-09-23)

- Added a read-only `today_weather.py` Streamlit module for a separate hourly
  Open-Meteo view of the current Kyiv-local day.
- The integration point is limited to one import, one additional tab, and one
  renderer call in `app.py`; `collector.py`, Google Sheets, model code, and
  existing tabs remain unchanged.
- The detailed view loads only after an explicit user action, is cached for 15
  minutes, supports manual refresh, and degrades to an in-tab warning when
  the external weather request is unavailable.

Стан на 2026-08-14 після аудиту якості прогнозу:

- Branch: `main`.
- Tracking: `origin/main`.
- Remote: `https://github.com/SergejKolesnik/Solar-Monitoring-System.git` (fetch/push).
- Working tree: локально має зміни, які треба закомітити/запушити після погодження.
- HEAD: `f567d6f Defer plan sheet loading` локально, `origin/main` відстає на 1 коміт до пушу.
- Основний Streamlit entry point: `app.py`.
- Production collector: `collector.py`.
- Google Sheets залишається operational source of truth.
- Supabase використовується як опціональний shadow sync.
- conventional automated tests: не знайдено.
- Camino Planner: присутній у `docs/camino/` як окремий GitHub Pages PWA.
- Read-only quality report за даними Google Sheets на 2026-08-14:
  - факти доступні до `2026-08-13 19:00`;
  - головним operational критерієм є погодинна якість прогнозу в МВт, бо підприємство планує наступну добу погодинно;
  - погодинна MAE за 7 днів: база 1.83 МВт, AI 1.09 МВт, покращення +40.7%, AI кращий у 80% продуктивних годин;
  - погодинна MAE за 14 днів: база 1.77 МВт, AI 0.95 МВт, покращення +46.1%, AI кращий у 83% продуктивних годин;
  - погодинна MAE за 30 днів: база 1.77 МВт, AI 1.27 МВт, покращення +28.0%, AI кращий у 73% продуктивних годин;
  - за 14 днів найбільше погодинне покращення видно зранку 06-09 (+60.4%) і ввечері 16-20 (+51.8%); у пікові години 10-15 покращення нижче (+38.0%) і саме там треба уважніше ловити хмарність;
  - добова MAPE за 7 днів: база 11.4%, AI 11.3%, покращення +0.8%;
  - добова MAPE за 14 днів: база 9.4%, AI 8.4%, покращення +10.4%;
  - добова MAPE за 30 днів: база 16.0%, AI 15.5%, покращення +3.5%;
  - shadow-корекція за 7/14 днів гірша за поточний AI, тому не готова до production promotion.

## Architectural decisions

- 2026-10-27: операційний сценарій закупівлі — прогноз погодинної генерації на наступну календарну добу, доступний користувачеві до 12:00 за Києвом попереднього дня; загальний rolling holdout не вважається доказом якості цього сценарію, доки backtest не відповідає такому cutoff.
- 2026-10-27: Supabase зберігає `forecast_run_at` і погодні snapshot-и окремо, однак перша версія collector кодувала naive UTC час як Europe/Kyiv. Старі backtest метрики не підтверджують cutoff до 12:00 і позначаються як provisional.
- 2026-10-27: перший vintage backtest знайшов 41 дату та 454 погодинні порівняння за записаними мітками, але зсув часу на 3 години робить цей зріз непридатним для бізнес-висновків. Після виправлення використовувати лише `source=collector_utc_v2`.
- 2026-10-27: попередні point-in-time walk-forward (+14.9% HGB за останні 14 дат) і fixed holdout метрики (+6.6% загалом, -7.6% у хмарності ≥70%) provisional через той самий зсув часу; production forecast не змінювався.
- 2026-10-27: production model gate має використовувати vintage-погодні ознаки, бо Google Sheet за останні 7 днів перезаписується історичними погодними спостереженнями; такий gate не є прямим аналогом day-ahead forecast.
- 2026-10-27: аудит виявив, що collector передавав naive UTC `datetime.now()` у Supabase як ніби це час Europe/Kyiv; legacy `source=collector` знімки можуть бути зсунуті на 3 години й не використовуються для підтвердження cutoff. Нові записи маркуються `collector_utc_v2`, мають явний UTC час, а vintage-backtest ігнорує legacy записи.
- 2026-10-27: PR #14 готує shadow-збереження Open-Meteo у `weather_forecasts` з `provider=open_meteo` та точні UTC мітки для нових forecast run-ів; збір почнеться після інтеграції зміни в production collector.
- 2026-10-27: сирі факти в Google Sheets не видаляються автоматично; модель, UI, read-only звіт і Supabase shadow-sync використовують спільний `valid_fact_mask` (позитивний факт, не майбутній, не вище 110% потужності).
- 2026-10-27: AI-корекція допускається до operational прогнозу тільки після хронологічної перевірки на невиданому моделі часовому відрізку; при провалі використовується базовий прогноз.
- 2026-10-27: неоднозначна осіння година Києва локалізується детерміновано; явний `DST` означає літній екземпляр, без суфікса використовується стандартний.

- 2026-08-11: зафіксовано, що Solar Python/Streamlit application є основним продуктом, а `docs/camino/` — окремим co-located компонентом без runtime-зв’язку.
- 2026-08-11: Google Sheets задокументовано як чинне operational-сховище; Supabase — як shadow-копію до окремого рішення про міграцію.
- 2026-08-11: production-моделлю вважається шлях `collector.py` з `HistGradientBoostingRegressor`; `model_engine.py` не вважається production без додаткового підтвердження.
- 2026-08-11: Google Sheets persistence зберігає identity чинного production worksheet. `_collector_staging` використовується для повного запису й перевірки, а atomic batch promotion змінює лише values; будь-яка staging, promotion або production-validation помилка зупиняє pipeline до Supabase sync.
- 2026-08-12: `auto_sync.yml` серіалізує production collector runs через GitHub Actions `concurrency`, щоб паралельні запуски не використовували спільний `_collector_staging` одночасно.
- 2026-08-27: додано контейнерний шлях деплою Streamlit UI. Перший production-hosting етап має переносити тільки web UI, залишаючи scheduled collector на GitHub Actions до окремого рішення.
