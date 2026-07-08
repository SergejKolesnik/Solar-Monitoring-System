# Camino del Norte 2026 Planner

## GitHub Pages

Ця копія PWA призначена для публікації з папки `docs/camino/` репозиторію `SergejKolesnik/Solar-Monitoring-System`.

Увімкнення Pages:

1. `GitHub` → `Settings` → `Pages`.
2. `Source`: `Deploy from branch`.
3. Branch: `main`.
4. Folder: `/docs`.
5. `Save`.

Очікуване посилання після деплою:

```text
https://sergejkolesnik.github.io/Solar-Monitoring-System/camino/
```

PWA використовує відносні шляхи, тому `index.html`, `manifest.json`, `service-worker.js` та icons працюють з підшляху `/Solar-Monitoring-System/camino/`.

Supabase URL/key не хардкодяться. Їх потрібно ввести у вкладці `☁️ Синхр.` у самому застосунку.

Мобільний офлайн travel-planner / PWA без фреймворків. Основний режим роботи локальний: `localStorage` + `IndexedDB`. Supabase-синхронізація є необов'язковою і використовується тільки для текстових даних.

## Запуск

PWA потрібно відкривати через HTTP, бо service worker не працює з `file://`.

```bash
python -m http.server 8080
```

На телефоні відкрийте:

```text
http://IP-АДРЕСА-КОМП'ЮТЕРА:8080/
```

## Встановлення PWA

Android / Chrome: меню `⋮` → `Додати на головний екран` або `Встановити застосунок`.

iPhone / Safari: `Поділитися` → `На Початковий екран`.

## Supabase Project

1. Зайдіть на [supabase.com](https://supabase.com/).
2. Створіть новий project.
3. Відкрийте `SQL Editor`.
4. Вставте SQL нижче і натисніть `Run`.
5. Відкрийте `Project Settings` → `API`.
6. Скопіюйте `Project URL` і `anon public key`.
7. У PWA відкрийте розділ `Синхр.` і вставте URL, anon key та код подорожі, наприклад `camino-2026`.

## SQL Schema

Цей SQL створює таблиці, індекси, `updated_at` тригери і прості RLS policies для персонального використання через anon key.

```sql
create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.trips (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  title text not null default 'Camino del Norte 2026',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.route_points (
  id text primary key,
  trip_code text not null references public.trips(code) on delete cascade,
  date text,
  time text,
  type text,
  from_place text,
  to_place text,
  title text,
  address text,
  note text,
  maps_url text,
  status text,
  sort_order int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.tickets (
  id text primary key,
  trip_code text not null references public.trips(code) on delete cascade,
  type text,
  title text,
  date text,
  related_point_id text,
  booking_number text,
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.expenses (
  id text primary key,
  trip_code text not null references public.trips(code) on delete cascade,
  category text,
  title text,
  amount numeric(12,2) not null default 0,
  currency text not null default 'EUR',
  date text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.notes (
  trip_code text primary key references public.trips(code) on delete cascade,
  content text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.checklists (
  trip_code text not null references public.trips(code) on delete cascade,
  list_key text not null,
  state jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (trip_code, list_key)
);

create index if not exists route_points_trip_code_sort_idx on public.route_points(trip_code, sort_order);
create index if not exists tickets_trip_code_idx on public.tickets(trip_code);
create index if not exists expenses_trip_code_idx on public.expenses(trip_code);
create unique index if not exists trips_code_unique_idx on public.trips(code);

drop trigger if exists trg_trips_updated_at on public.trips;
create trigger trg_trips_updated_at
before update on public.trips
for each row execute function public.set_updated_at();

drop trigger if exists trg_route_points_updated_at on public.route_points;
create trigger trg_route_points_updated_at
before update on public.route_points
for each row execute function public.set_updated_at();

drop trigger if exists trg_tickets_updated_at on public.tickets;
create trigger trg_tickets_updated_at
before update on public.tickets
for each row execute function public.set_updated_at();

drop trigger if exists trg_expenses_updated_at on public.expenses;
create trigger trg_expenses_updated_at
before update on public.expenses
for each row execute function public.set_updated_at();

drop trigger if exists trg_notes_updated_at on public.notes;
create trigger trg_notes_updated_at
before update on public.notes
for each row execute function public.set_updated_at();

drop trigger if exists trg_checklists_updated_at on public.checklists;
create trigger trg_checklists_updated_at
before update on public.checklists
for each row execute function public.set_updated_at();

alter table public.trips enable row level security;
alter table public.route_points enable row level security;
alter table public.tickets enable row level security;
alter table public.expenses enable row level security;
alter table public.notes enable row level security;
alter table public.checklists enable row level security;

drop policy if exists "anon_all_trips" on public.trips;
create policy "anon_all_trips" on public.trips
for all to anon using (true) with check (true);

drop policy if exists "anon_all_route_points" on public.route_points;
create policy "anon_all_route_points" on public.route_points
for all to anon using (true) with check (true);

drop policy if exists "anon_all_tickets" on public.tickets;
create policy "anon_all_tickets" on public.tickets
for all to anon using (true) with check (true);

drop policy if exists "anon_all_expenses" on public.expenses;
create policy "anon_all_expenses" on public.expenses
for all to anon using (true) with check (true);

drop policy if exists "anon_all_notes" on public.notes;
create policy "anon_all_notes" on public.notes
for all to anon using (true) with check (true);

drop policy if exists "anon_all_checklists" on public.checklists;
create policy "anon_all_checklists" on public.checklists
for all to anon using (true) with check (true);
```

Важливо: ці RLS policies відкривають таблиці для anon key. Для приватного персонального project це найпростіший режим. Не публікуйте URL/key у відкритому репозиторії. Для публічного multi-user сценарію потрібна Supabase Auth і жорсткіші policies.

## Як підключити перший телефон

1. Встановіть PWA.
2. Відкрийте `Синхр.`.
3. Введіть Supabase URL, anon key і код подорожі.
4. Натисніть `Підключити`.
5. Натисніть `Перевірити Supabase`.
6. Якщо статус `Supabase працює`, натисніть `Завантажити локальні дані в хмару`.

## Як підключити другий телефон

1. Встановіть PWA на другому телефоні.
2. Введіть той самий Supabase URL, anon key і той самий код подорожі.
3. Натисніть `Підключити`.
4. Натисніть `Підтягнути дані з хмари`.
5. Далі використовуйте `Синхронізувати зараз`.

## Що синхронізується

- маршрутні точки;
- квитки та бронювання без файлів;
- бюджет;
- нотатки;
- стани чек-листів.

Синхронізація порівнює `updated_at` і використовує правило `lastUpdated wins`.

## Що поки не синхронізується

Скріншоти квитків, PDF і вкладення зберігаються тільки на цьому пристрої в IndexedDB. Для другого телефона їх потрібно додати окремо.

## Як перевірити синхронізацію

У розділі `Синхр.` натисніть `Перевірити Supabase`.

Кнопка:

- створює або оновлює trip;
- записує тестову точку маршруту;
- читає її назад;
- показує `Supabase працює` або конкретну помилку.

Останні 10 подій видно в журналі синхронізації.

## Офлайн режим

Якщо Supabase не налаштовано, CDN недоступний або немає інтернету, застосунок не падає і продовжує працювати локально.

Локальні дані:

- маршрут, квитки, бюджет, нотатки, чек-листи, sync config - `localStorage`;
- скріни, PDF і вкладення - `IndexedDB`.

## Експорт та імпорт

У розділі `Дані` можна експортувати або імпортувати JSON. Файли не входять у JSON-експорт.
