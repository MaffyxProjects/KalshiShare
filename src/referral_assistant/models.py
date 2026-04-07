from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ComplianceStatus(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    AMBIGUOUS = "ambiguous"


class DraftStatus(str, Enum):
    QUEUED_FOR_MANUAL_REVIEW = "queued_for_manual_review"
    BLOCKED_BY_COMPLIANCE = "blocked_by_compliance"
    BLOCKED_BY_MODEL = "blocked_by_model"
    DEFERRED_BY_CAP = "deferred_by_cap"
    MANUALLY_POSTED = "manually_posted"
    DISMISSED = "dismissed"
    VISIBILITY_VERIFIED = "visibility_verified"


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class VisibilityStatus(str, Enum):
    VISIBLE = "visible"
    NOT_VISIBLE = "not_visible"
    INCONCLUSIVE = "inconclusive"


class Persona(str, Enum):
    ANALYST = "Analyst"
    HUNTER = "Hunter"
    NONE = "None"


@dataclass(slots=True)
class Opportunity:
    source: str
    source_item_id: str
    source_url: str
    community_name: str
    author_name: str
    title: str
    body: str
    created_at: datetime
    discovered_at: datetime = field(default_factory=utc_now)
    keyword_hits: list[str] = field(default_factory=list)
    thread_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def dedupe_key(self) -> str:
        raw = "|".join(
            [
                self.source.strip().lower(),
                self.source_item_id.strip().lower(),
                self.community_name.strip().lower(),
                self.author_name.strip().lower(),
                self.source_url.strip().lower(),
            ]
        )
        return sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_at"] = self.created_at.isoformat()
        payload["discovered_at"] = self.discovered_at.isoformat()
        return payload


@dataclass(slots=True)
class ComplianceEvidence:
    status: ComplianceStatus
    reason_codes: list[str]
    summary: str
    evidence_lines: list[str]
    allow_matches: list[str] = field(default_factory=list)
    deny_matches: list[str] = field(default_factory=list)

    @property
    def is_allowed(self) -> bool:
        return self.status == ComplianceStatus.ALLOWED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GeminiDecision:
    eligible: bool
    reason_codes: list[str]
    chosen_persona: Persona
    disclosure_required: bool
    reply_text: str
    confidence: float
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["chosen_persona"] = self.chosen_persona.value
        return payload


@dataclass(slots=True)
class DraftRecord:
    opportunity: Opportunity
    compliance: ComplianceEvidence
    decision: GeminiDecision
    status: DraftStatus
    id: int | None = None
    operator_notes: str = ""
    public_post_url: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "id": self.id,
            "status": self.status.value,
            "operator_notes": self.operator_notes,
            "public_post_url": self.public_post_url,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "opportunity": self.opportunity.to_dict(),
            "compliance": self.compliance.to_dict(),
            "decision": self.decision.to_dict(),
        }
        return payload


@dataclass(slots=True)
class AlertEvent:
    event_type: str
    message: str
    level: AlertLevel = AlertLevel.INFO
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["level"] = self.level.value
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class VisibilityCheckResult:
    lead_id: int
    status: VisibilityStatus
    checked_url: str
    expected_snippet: str
    details: str
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["created_at"] = self.created_at.isoformat()
        return payload


@dataclass(slots=True)
class KillSwitchState:
    enabled: bool
    changed_at: datetime = field(default_factory=utc_now)
    changed_by: str = "system"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["changed_at"] = self.changed_at.isoformat()
        return payload
