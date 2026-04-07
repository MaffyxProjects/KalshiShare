from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from referral_assistant.adapters.base import RulesContext
from referral_assistant.db import Database
from referral_assistant.models import ComplianceEvidence, ComplianceStatus, GeminiDecision, Opportunity, Persona
from referral_assistant.scheduler import ReferralScheduler
from referral_assistant.services.compliance import ComplianceParser
from referral_assistant.services.scoring import CandidateScorer


@dataclass
class DummyCandidate:
    candidate_id: str


class DummyAdapter:
    source_name = "dummy"

    def fetch_candidates(self):
        return [DummyCandidate(candidate_id="abc123")]

    def fetch_rules_context(self, candidate):
        return RulesContext(
            community_name="beermoney",
            rules_text="Referral links are allowed here.",
            sources=["sidebar"],
        )

    def normalize(self, candidate):
        return Opportunity(
            source="dummy",
            source_item_id=candidate.candidate_id,
            source_url="https://example.com/thread",
            community_name="beermoney",
            author_name="tester",
            title="Kalshi sign up bonus",
            body="Kalshi and passive income thread",
            created_at=datetime.now(timezone.utc),
            thread_metadata={"score": 10, "num_comments": 4},
        )

    def build_open_url(self, opportunity):
        return opportunity.source_url

    def supports_manual_publish(self):
        return True


class DummyGeminiService:
    def decide(self, opportunity, compliance):
        return GeminiDecision(
            eligible=True,
            reason_codes=["rules_allow_referrals"],
            chosen_persona=Persona.HUNTER,
            disclosure_required=True,
            reply_text="{{disclosure_line}}\n\nUse {{referral_link}}",
            confidence=0.91,
            rationale="Great fit.",
        )


class DummyNotifier:
    def __init__(self):
        self.events = []

    def send(self, event):
        self.events.append(event)
        return True


def test_scheduler_queues_manual_review_record(tmp_path) -> None:
    database = Database(tmp_path / "assistant.db")
    database.initialize()
    notifier = DummyNotifier()
    scheduler = ReferralScheduler(
        database=database,
        logger=logging.getLogger("scheduler-test"),
        adapters=[DummyAdapter()],
        compliance_parser=ComplianceParser(),
        scorer=CandidateScorer(["Kalshi", "passive income"]),
        gemini_service=DummyGeminiService(),
        notifier=notifier,
        max_daily_candidates=5,
        max_daily_drafts=5,
        high_confidence_threshold=0.8,
    )

    summary = scheduler.run_once()
    records = database.list_draft_records()

    assert summary.processed_candidates == 1
    assert summary.queued_drafts == 1
    assert len(records) == 1
    assert records[0].status.value == "queued_for_manual_review"
    assert notifier.events


def test_scheduler_respects_daily_draft_cap(tmp_path) -> None:
    database = Database(tmp_path / "assistant.db")
    database.initialize()
    database.increment_counter("drafts", amount=1)
    scheduler = ReferralScheduler(
        database=database,
        logger=logging.getLogger("scheduler-test-cap"),
        adapters=[DummyAdapter()],
        compliance_parser=ComplianceParser(),
        scorer=CandidateScorer(["Kalshi"]),
        gemini_service=DummyGeminiService(),
        notifier=DummyNotifier(),
        max_daily_candidates=5,
        max_daily_drafts=1,
        high_confidence_threshold=0.8,
    )

    summary = scheduler.run_once()
    records = database.list_draft_records()

    assert summary.queued_drafts == 0
    assert summary.blocked_candidates == 1
    assert records[0].status.value == "deferred_by_cap"
