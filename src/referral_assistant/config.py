from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    root_dir: Path
    database_path: Path
    log_path: Path
    export_dir: Path
    subreddits: list[str]
    keywords: list[str]
    max_daily_candidates: int
    max_daily_drafts: int
    reddit_hot_limit: int
    reddit_new_limit: int
    high_confidence_threshold: float
    gemini_model: str
    referral_url: str
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str
    gemini_api_key: str
    discord_webhook_url: str

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)


def load_settings(root_dir: str | Path | None = None) -> Settings:
    resolved_root = Path(root_dir or Path.cwd()).resolve()
    _load_env_file(resolved_root / ".env")

    database_path = resolved_root / os.getenv(
        "REFERRAL_ASSISTANT_DB_PATH", "data/referral_assistant.db"
    )
    log_path = resolved_root / os.getenv(
        "REFERRAL_ASSISTANT_LOG_PATH", "data/referral_assistant.log"
    )
    export_dir = resolved_root / os.getenv("REFERRAL_ASSISTANT_EXPORT_DIR", "exports")

    settings = Settings(
        root_dir=resolved_root,
        database_path=database_path,
        log_path=log_path,
        export_dir=export_dir,
        subreddits=_split_csv(
            os.getenv("REFERRAL_ASSISTANT_SUBREDDITS", "beermoney,signupsforpay")
        ),
        keywords=_split_csv(
            os.getenv(
                "REFERRAL_ASSISTANT_KEYWORDS",
                "Kalshi,prediction markets,Fed rates,passive income",
            )
        ),
        max_daily_candidates=int(
            os.getenv("REFERRAL_ASSISTANT_MAX_DAILY_CANDIDATES", "25")
        ),
        max_daily_drafts=int(os.getenv("REFERRAL_ASSISTANT_MAX_DAILY_DRAFTS", "10")),
        reddit_hot_limit=int(os.getenv("REFERRAL_ASSISTANT_REDDIT_HOT_LIMIT", "25")),
        reddit_new_limit=int(os.getenv("REFERRAL_ASSISTANT_REDDIT_NEW_LIMIT", "25")),
        high_confidence_threshold=float(
            os.getenv("REFERRAL_ASSISTANT_HIGH_CONFIDENCE_THRESHOLD", "0.8")
        ),
        gemini_model=os.getenv(
            "REFERRAL_ASSISTANT_GEMINI_MODEL", "gemini-1.5-flash"
        ),
        referral_url=os.getenv("REFERRAL_ASSISTANT_REFERRAL_URL", "").strip(),
        reddit_client_id=os.getenv("REFERRAL_ASSISTANT_REDDIT_CLIENT_ID", ""),
        reddit_client_secret=os.getenv("REFERRAL_ASSISTANT_REDDIT_CLIENT_SECRET", ""),
        reddit_user_agent=os.getenv(
            "REFERRAL_ASSISTANT_REDDIT_USER_AGENT",
            "referral-draft-assistant/0.1 by local-operator",
        ),
        gemini_api_key=os.getenv("REFERRAL_ASSISTANT_GEMINI_API_KEY", ""),
        discord_webhook_url=os.getenv("REFERRAL_ASSISTANT_DISCORD_WEBHOOK_URL", ""),
    )
    settings.ensure_directories()
    return settings
