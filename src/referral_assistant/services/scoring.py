from __future__ import annotations

from datetime import datetime, timezone

from referral_assistant.models import Opportunity


class CandidateScorer:
    def __init__(self, keywords: list[str]) -> None:
        self.keywords = [keyword.strip() for keyword in keywords if keyword.strip()]

    def score(self, opportunity: Opportunity) -> float:
        haystack = " ".join(
            [
                opportunity.title,
                opportunity.body,
                str(opportunity.thread_metadata.get("external_url", "")),
            ]
        ).lower()
        hits: list[str] = []
        for keyword in self.keywords:
            if keyword.lower() in haystack:
                hits.append(keyword)
        opportunity.keyword_hits = hits

        thread_score = float(opportunity.thread_metadata.get("score", 0))
        comment_count = float(opportunity.thread_metadata.get("num_comments", 0))
        age_hours = max(
            (datetime.now(timezone.utc) - opportunity.created_at).total_seconds() / 3600,
            0.0,
        )
        freshness_boost = max(0.0, 12.0 - min(age_hours, 12.0))
        return round(
            len(hits) * 10.0
            + min(thread_score, 50.0) * 0.2
            + min(comment_count, 50.0) * 0.1
            + freshness_boost,
            2,
        )
