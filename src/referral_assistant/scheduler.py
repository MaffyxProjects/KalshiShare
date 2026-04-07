from __future__ import annotations

from dataclasses import dataclass
import logging

from referral_assistant.adapters.base import SourceAdapter
from referral_assistant.db import Database
from referral_assistant.models import (
    AlertEvent,
    AlertLevel,
    DraftRecord,
    DraftStatus,
    GeminiDecision,
    Persona,
)
from referral_assistant.services.alerts import DiscordWebhookNotifier
from referral_assistant.services.compliance import ComplianceParser
from referral_assistant.services.gemini_service import GeminiService, GeminiServiceError
from referral_assistant.services.scoring import CandidateScorer


@dataclass(slots=True)
class SchedulerSummary:
    processed_candidates: int = 0
    skipped_duplicates: int = 0
    queued_drafts: int = 0
    blocked_candidates: int = 0
    errors: int = 0


class ReferralScheduler:
    def __init__(
        self,
        database: Database,
        logger: logging.Logger,
        adapters: list[SourceAdapter],
        compliance_parser: ComplianceParser,
        scorer: CandidateScorer,
        gemini_service: GeminiService,
        notifier: DiscordWebhookNotifier,
        max_daily_candidates: int,
        max_daily_drafts: int,
        high_confidence_threshold: float,
    ) -> None:
        self.database = database
        self.logger = logger
        self.adapters = adapters
        self.compliance_parser = compliance_parser
        self.scorer = scorer
        self.gemini_service = gemini_service
        self.notifier = notifier
        self.max_daily_candidates = max_daily_candidates
        self.max_daily_drafts = max_daily_drafts
        self.high_confidence_threshold = high_confidence_threshold

    def run_once(self) -> SchedulerSummary:
        summary = SchedulerSummary()
        if self.database.get_kill_switch_state().enabled:
            message = "Kill switch enabled. Scheduler run exited without processing."
            self.logger.warning(message)
            self.database.log_event(
                AlertEvent(
                    event_type="kill_switch_enabled",
                    level=AlertLevel.WARNING,
                    message=message,
                )
            )
            return summary

        for adapter in self.adapters:
            try:
                candidates = adapter.fetch_candidates()
            except Exception as exc:
                summary.errors += 1
                self._record_error(
                    error_type="candidate_fetch_error",
                    message=str(exc),
                    metadata={"adapter": adapter.source_name},
                )
                continue

            for candidate in candidates:
                if self.database.get_counter("candidates") >= self.max_daily_candidates:
                    self.logger.info("Daily candidate cap reached; stopping scheduler.")
                    return summary

                try:
                    opportunity = adapter.normalize(candidate)
                    if self.database.lead_exists(opportunity.dedupe_key):
                        summary.skipped_duplicates += 1
                        continue

                    rules_context = adapter.fetch_rules_context(candidate)
                    compliance = self.compliance_parser.evaluate(rules_context)
                    score = self.scorer.score(opportunity)
                    self.database.increment_counter("candidates")
                    summary.processed_candidates += 1

                    if not compliance.is_allowed:
                        decision = GeminiDecision(
                            eligible=False,
                            reason_codes=compliance.reason_codes,
                            chosen_persona=Persona.NONE,
                            disclosure_required=True,
                            reply_text="",
                            confidence=0.0,
                            rationale="Compliance gate blocked this item.",
                        )
                        status = DraftStatus.BLOCKED_BY_COMPLIANCE
                        summary.blocked_candidates += 1
                    elif self.database.get_counter("drafts") >= self.max_daily_drafts:
                        decision = GeminiDecision(
                            eligible=False,
                            reason_codes=["daily_draft_cap_reached"],
                            chosen_persona=Persona.NONE,
                            disclosure_required=True,
                            reply_text="",
                            confidence=0.0,
                            rationale="Daily draft cap reached before Gemini evaluation.",
                        )
                        status = DraftStatus.DEFERRED_BY_CAP
                        summary.blocked_candidates += 1
                    else:
                        decision = self.gemini_service.decide(opportunity, compliance)
                        status = (
                            DraftStatus.QUEUED_FOR_MANUAL_REVIEW
                            if decision.eligible
                            else DraftStatus.BLOCKED_BY_MODEL
                        )
                        if decision.eligible:
                            self.database.increment_counter("drafts")
                            summary.queued_drafts += 1
                        else:
                            summary.blocked_candidates += 1

                    record = DraftRecord(
                        opportunity=opportunity,
                        compliance=compliance,
                        decision=decision,
                        status=status,
                    )
                    lead_id = self.database.save_draft_record(record, score=score)
                    self.database.log_event(
                        AlertEvent(
                            event_type="lead_processed",
                            message=f"Processed {opportunity.source}:{opportunity.source_item_id}",
                            metadata={
                                "lead_id": lead_id,
                                "status": status.value,
                                "community": opportunity.community_name,
                                "score": score,
                            },
                        )
                    )

                    if (
                        status == DraftStatus.QUEUED_FOR_MANUAL_REVIEW
                        and decision.confidence >= self.high_confidence_threshold
                    ):
                        self._notify(
                            AlertEvent(
                                event_type="high_confidence_draft",
                                message=f"High-confidence draft queued for r/{opportunity.community_name}.",
                                metadata={
                                    "lead_id": lead_id,
                                    "persona": decision.chosen_persona.value,
                                    "confidence": decision.confidence,
                                    "source_url": opportunity.source_url,
                                },
                            )
                        )

                except GeminiServiceError as exc:
                    summary.errors += 1
                    self._record_error(
                        error_type="gemini_error",
                        message=str(exc),
                        metadata={"adapter": adapter.source_name},
                    )
                except Exception as exc:
                    summary.errors += 1
                    self._record_error(
                        error_type="scheduler_error",
                        message=str(exc),
                        metadata={"adapter": adapter.source_name},
                    )

        return summary

    def _record_error(
        self,
        error_type: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        context = metadata or {}
        self.logger.exception("%s: %s", error_type, message)
        self.database.log_error(error_type=error_type, message=message, context=context)
        self._notify(
            AlertEvent(
                event_type=error_type,
                level=AlertLevel.ERROR,
                message=message,
                metadata=context,
            )
        )

    def _notify(self, event: AlertEvent) -> None:
        self.database.log_event(event)
        try:
            self.notifier.send(event)
        except Exception as exc:
            self.logger.warning("Discord webhook send failed: %s", exc)
