from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from referral_assistant.adapters.reddit import RedditAdapter
from referral_assistant.config import Settings, load_settings
from referral_assistant.db import Database
from referral_assistant.logging_utils import configure_logging
from referral_assistant.scheduler import ReferralScheduler
from referral_assistant.services.alerts import DiscordWebhookNotifier
from referral_assistant.services.compliance import ComplianceParser
from referral_assistant.services.gemini_service import GeminiService
from referral_assistant.services.manual_review import ManualPublishHelper
from referral_assistant.services.scoring import CandidateScorer
from referral_assistant.services.visibility import VisibilityVerifier


@dataclass(slots=True)
class AppContext:
    settings: Settings
    logger: logging.Logger
    database: Database
    scheduler: ReferralScheduler
    notifier: DiscordWebhookNotifier
    review_helper: ManualPublishHelper
    visibility_verifier: VisibilityVerifier


def create_app_context(root_dir: str | Path | None = None) -> AppContext:
    settings = load_settings(root_dir=root_dir)
    logger = configure_logging(settings.log_path)
    database = Database(settings.database_path)
    database.initialize()

    compliance_parser = ComplianceParser()
    scorer = CandidateScorer(settings.keywords)
    gemini_service = GeminiService(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
    )
    notifier = DiscordWebhookNotifier(settings.discord_webhook_url)
    review_helper = ManualPublishHelper(settings.referral_url)
    visibility_verifier = VisibilityVerifier()
    adapters = [RedditAdapter(settings)]

    scheduler = ReferralScheduler(
        database=database,
        logger=logger,
        adapters=adapters,
        compliance_parser=compliance_parser,
        scorer=scorer,
        gemini_service=gemini_service,
        notifier=notifier,
        max_daily_candidates=settings.max_daily_candidates,
        max_daily_drafts=settings.max_daily_drafts,
        high_confidence_threshold=settings.high_confidence_threshold,
    )

    return AppContext(
        settings=settings,
        logger=logger,
        database=database,
        scheduler=scheduler,
        notifier=notifier,
        review_helper=review_helper,
        visibility_verifier=visibility_verifier,
    )
