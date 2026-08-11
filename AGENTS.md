# Codex working agreement

## Project identity

- The primary project in this repository is **SkyGrid Solar AI**, a Streamlit system for monitoring and forecasting solar generation at the Nikopol Ferroalloy Plant (НЗФ).
- Treat the Python/Streamlit solar application as the main product. The Camino Planner under `docs/camino/` is a separate co-located PWA and must not be mixed into the solar architecture or feature work.
- GitHub (`origin`) is the source of truth used to continue work between the work and home PCs.

## Before making changes

1. Confirm that the working directory is this repository.
2. Check the current branch with `git branch --show-current`.
3. Check `git status` and preserve unrelated local changes.
4. Read `PROJECT_CONTEXT.md` and the relevant implementation files before editing.

## Safety rules

- Never run destructive Git operations (`reset`, forced checkout/restore, clean, rebase, force-push, or history rewriting) without explicit user permission.
- Do not commit, push, pull, switch branches, or modify remotes unless the user explicitly asks.
- Do not change or expose secrets, API keys, `.env` files, Streamlit Secrets, Google credentials, email credentials, Supabase credentials, or production configuration without an explicit request.
- Preserve Streamlit deployment compatibility. Treat `app.py`, `requirements.txt`, `.streamlit/`, and `.github/workflows/` as deployment-sensitive.
- Do not mix SkyGrid Solar AI functionality with Camino Planner. Changes under `docs/camino/` require an explicit Camino-specific request.
- Preserve the current architecture unless there is a documented, evidence-based reason to change it. Prefer small, backward-compatible changes over parallel implementations.
- Do not commit large generated files, caches, exports, model artifacts, or datasets unless they are necessary and explicitly intended for version control.

## Validation and documentation

- After changes, run the available tests and safe checks appropriate to the touched code. At minimum, validate Python syntax and run `git diff --check` when Python or documentation files change.
- The repository currently has no conventional automated unit-test suite; `test_lab.py` is a manual Streamlit visualization sandbox, not a unit test.
- Do not claim runtime or deployment success if required dependencies, credentials, network access, or production data are unavailable.
- When behavior, configuration, deployment, data contracts, or architecture changes, update `README.md` and `PROJECT_CONTEXT.md` as applicable.
- Record important architectural decisions briefly in the “Architectural decisions” section of `PROJECT_CONTEXT.md`.
