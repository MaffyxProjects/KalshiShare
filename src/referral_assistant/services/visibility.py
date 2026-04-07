from __future__ import annotations

from dataclasses import dataclass

import requests

from referral_assistant.models import VisibilityCheckResult, VisibilityStatus


REMOVAL_MARKERS = [
    "comment removed",
    "removed by moderator",
    "this comment has been removed",
    "[removed]",
    "[deleted]",
]


@dataclass(slots=True)
class VisibilityVerifier:
    timeout_seconds: int = 15

    def verify_visibility(
        self,
        lead_id: int,
        public_url: str,
        expected_snippet: str,
    ) -> VisibilityCheckResult:
        try:
            response = requests.get(
                public_url,
                headers={"User-Agent": "Mozilla/5.0 referral-draft-assistant visibility-check"},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            return VisibilityCheckResult(
                lead_id=lead_id,
                status=VisibilityStatus.INCONCLUSIVE,
                checked_url=public_url,
                expected_snippet=expected_snippet,
                details=f"Anonymous fetch failed: {exc}",
            )

        if response.status_code >= 400:
            return VisibilityCheckResult(
                lead_id=lead_id,
                status=VisibilityStatus.INCONCLUSIVE,
                checked_url=public_url,
                expected_snippet=expected_snippet,
                details=f"Anonymous fetch returned status code {response.status_code}.",
            )

        page_text = response.text.lower()
        target = expected_snippet.strip().lower()
        if target and target in page_text:
            return VisibilityCheckResult(
                lead_id=lead_id,
                status=VisibilityStatus.VISIBLE,
                checked_url=public_url,
                expected_snippet=expected_snippet,
                details="Expected snippet was visible in the anonymous response.",
            )

        if any(marker in page_text for marker in REMOVAL_MARKERS):
            return VisibilityCheckResult(
                lead_id=lead_id,
                status=VisibilityStatus.NOT_VISIBLE,
                checked_url=public_url,
                expected_snippet=expected_snippet,
                details="The anonymous response included removal markers and not the expected snippet.",
            )

        return VisibilityCheckResult(
            lead_id=lead_id,
            status=VisibilityStatus.INCONCLUSIVE,
            checked_url=public_url,
            expected_snippet=expected_snippet,
            details="The anonymous response did not contain the expected snippet or a clear removal marker.",
        )
