# Changelog

All notable project changes are recorded here so future sessions can continue with full context.

## 2026-04-07

### Added
- Local Flask dashboard with server routes for overview, inbox, draft review, logs, exports, scheduler runs, and kill-switch control.
- HTML templates and a local stylesheet for the new dashboard so the UI no longer depends on Streamlit or pandas.
- Dashboard CLI entrypoint: `referral-assistant-dashboard`.
- Desktop launcher GUI built with Tkinter, including textboxes for host/port and buttons for database init, scheduler runs, dashboard start/stop, URL copy, and browser open.
- Double-click launcher entry at the repo root: `launch_referral_assistant.pyw`.
- One-click `Launch Everything` workflow in the launcher that initializes the database, starts the dashboard, and opens the browser automatically.
- Launcher now auto-detects a compatible Python runtime with `requests` and `flask` instead of assuming the interpreter that opened the `.pyw` file can run backend commands.
- Root `.env` file created with placeholder credentials and default local settings so operators can fill in secrets directly.
- Repository `.gitignore` added so local secrets, generated data, caches, and exports stay out of GitHub uploads.

### Changed
- Replaced the Streamlit-based monitoring UI with a Flask implementation served on `http://localhost:8501`.
- Updated package metadata to depend on Flask and include dashboard template/static assets in installations.
- Updated the README and blueprint docs to use the Flask dashboard launch flow.
- Lowered the declared Python requirement to `>=3.10` to match the verified runtime used during implementation.
- Added dashboard CLI argument parsing for custom host/port values and CLI module invocation for launcher-driven commands.
- Updated the dashboard console script to target the argument-aware entrypoint.
- Updated launcher copy so the window itself directs users to the one-click startup flow.
- Restyled the launcher with a hero header, status badge, card layout, and a darker console panel while restoring the deleted launcher module.
- Added launcher preflight messaging for optional modules like `praw` and `google.generativeai` so missing scheduler dependencies are surfaced early.
- Made the launcher scrollable and rearranged the action buttons into a denser two-column layout so controls do not get cut off at smaller window heights or higher display scaling.
- Switched launcher subprocesses to Windows hidden-window mode so dashboard and CLI startup no longer leave open command windows behind.

## 2026-04-06

### Added
- Project scaffold with `pyproject.toml`, `README.md`, `.env.example`, and `src/` / `tests/` / `docs/` directories.
- Core shared models for opportunities, compliance evidence, Gemini decisions, draft records, alerts, visibility checks, and kill-switch state.
- Local settings loader with `.env` support and directory bootstrapping.
- Logging utilities for file-backed runtime logs.
- `SourceAdapter` base contract and rules-context model.
- SQLite persistence layer with `lead_tracker`, `events`, `errors`, `visibility_checks`, and `system_state` tables.
- Compliance parser service with explicit-allow / explicit-deny / ambiguous rule handling.
- Candidate scoring service for keyword, freshness, and engagement ranking.
- Manual publish helper with disclosure and referral-link token rendering.
- Discord webhook notifier and anonymous visibility verifier services.
- Gemini decision service with strict JSON parsing, schema validation, persona selection, and tokenized referral/disclosure placeholders.
- Reddit adapter using PRAW for `hot` and `new` ingestion plus sidebar, rules, and sticky-context gathering.
- Scheduler orchestration for dedupe checks, compliance gating, daily caps, Gemini decisions, event logging, and Discord alerts.
- Runtime bootstrap and CLI commands for database initialization and one-shot scheduler runs.
- Runtime context now exposes the Discord notifier so dashboard-driven operator actions can emit alerts too.
- Streamlit dashboard with overview metrics, persona charting, manual-review inbox, posting/visibility workflows, runtime logs, exports, deferred-record views, scheduler trigger, and kill-switch controls.
- Dashboard alert delivery now uses best-effort webhook sends so UI actions still complete when Discord is unavailable or unconfigured.
- Test suite covering compliance parsing, Gemini JSON validation, anonymous visibility checks, and scheduler/manual-review behavior.
- Architecture blueprint document with the requested text diagram, flowchart, and pseudo-code sections.

### Changed
- Added configurable referral URL support to environment settings.
- Added `deferred_by_cap` as a draft lifecycle state for daily draft throttling.
- Normalized the README blueprint link and updated this changelog to reflect the completed implementation state.

### Notes
- Initial implementation completed and verified with compile checks, automated tests, and a CLI database initialization smoke test.
