from __future__ import annotations

from dataclasses import dataclass
import re

from referral_assistant.adapters.base import RulesContext
from referral_assistant.models import ComplianceEvidence, ComplianceStatus


ALLOW_PATTERNS = [
    re.compile(
        r"(referral|affiliate|promo|bonus|signup|sign up).{0,40}(allowed|ok|okay|welcome|permitted)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(allowed|ok|okay|welcome|permitted).{0,40}(referral|affiliate|promo|bonus|signup|sign up)",
        re.IGNORECASE,
    ),
]

DENY_PATTERNS = [
    re.compile(
        r"(no|not|without).{0,25}(referral|affiliate|promo|bonus|signup|sign up)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(referral|affiliate|promo|bonus|signup|sign up).{0,25}(prohibited|forbidden|banned|not allowed|removed)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(self[- ]promo|spam).{0,25}(not allowed|prohibited|banned|removed)",
        re.IGNORECASE,
    ),
]

INTEREST_PATTERNS = [
    re.compile(r"referral", re.IGNORECASE),
    re.compile(r"affiliate", re.IGNORECASE),
    re.compile(r"promo", re.IGNORECASE),
    re.compile(r"bonus", re.IGNORECASE),
    re.compile(r"signup|sign up", re.IGNORECASE),
]


@dataclass(slots=True)
class ComplianceParser:
    def evaluate(self, context: RulesContext) -> ComplianceEvidence:
        lines = [line.strip() for line in context.rules_text.splitlines() if line.strip()]
        allow_matches = [line for line in lines if _matches_any(line, ALLOW_PATTERNS)]
        deny_matches = [line for line in lines if _matches_any(line, DENY_PATTERNS)]
        evidence_lines = [line for line in lines if _matches_any(line, INTEREST_PATTERNS)]

        if deny_matches:
            return ComplianceEvidence(
                status=ComplianceStatus.BLOCKED,
                reason_codes=["rules_explicitly_block_referrals"],
                summary=f"{context.community_name} rules explicitly block referral or promo activity.",
                evidence_lines=evidence_lines or deny_matches,
                allow_matches=allow_matches,
                deny_matches=deny_matches,
            )

        if allow_matches:
            return ComplianceEvidence(
                status=ComplianceStatus.ALLOWED,
                reason_codes=["rules_allow_referrals"],
                summary=f"{context.community_name} rules explicitly allow referral or signup promotion.",
                evidence_lines=evidence_lines or allow_matches,
                allow_matches=allow_matches,
                deny_matches=deny_matches,
            )

        return ComplianceEvidence(
            status=ComplianceStatus.AMBIGUOUS,
            reason_codes=["rules_ambiguous_blocked_by_default"],
            summary=f"{context.community_name} rules do not explicitly allow referrals, so the item is blocked by default.",
            evidence_lines=evidence_lines,
            allow_matches=allow_matches,
            deny_matches=deny_matches,
        )


def _matches_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)
