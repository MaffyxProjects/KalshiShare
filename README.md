# Referral Draft Assistant

Referral Draft Assistant is a local-only Python application for compliant opportunity discovery, moderation-rule screening, Gemini-powered draft generation, manual review, visibility checks, and audit logging.

## Guardrails

- No automated posting to third-party platforms.
- No paid infrastructure, proxies, or cloud hosting.
- No unsupported scraping around platform access controls.
- No draft generation when moderation rules are ambiguous.
- All referral copy is manual-review only and includes disclosure guidance.

## Components

- `SourceAdapter` contract for compliant ingestion sources.
- Reddit adapter using PRAW for `hot` and `new` streams.
- Compliance parser that blocks on ambiguous subreddit rules.
- Gemini decision engine that returns strict JSON.
- SQLite persistence for leads, events, errors, visibility checks, and system state.
- Discord webhook alerts for high-confidence drafts, failures, and kill-switch changes.
- Flask dashboard for queue review, metrics, logs, exports, and controls.
- Tkinter launcher for starting the dashboard and common local actions without terminal commands.

## Quick Start

1. Create a virtual environment and install the package:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -e .[dev]
   ```

2. Copy `.env.example` to `.env` and fill in your local settings.

3. Launch the desktop launcher:

   ```powershell
   referral-assistant-launcher
   ```

   Or on Windows, double-click [launch_referral_assistant.pyw](E:\Google%20Drive\Generated%20Ideas\KalshiShare\launch_referral_assistant.pyw).

4. In the launcher window:
- Set `Host` and `Port` if you want something other than `127.0.0.1:8501`.
- Click `Launch Everything`.
- After that, use `Run Scheduler Once` whenever you want an ingestion/drafting pass.

5. Optional direct commands if you still want them:

   ```powershell
   referral-assistant-init-db
   referral-assistant-run-once
   referral-assistant-dashboard
   ```

The dashboard runs on `http://localhost:8501`.

## Architecture

`Source Adapters -> Normalizer -> Compliance Parser -> Gemini Decision Engine -> SQLite/Event Log -> Dashboard/Discord Alerts -> Manual Publish Helper -> Optional Public Visibility Check`

See [docs/blueprint.md](docs/blueprint.md) for the text flowchart, pseudo-code, and architecture notes.
