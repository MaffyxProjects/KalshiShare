from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from referral_assistant.adapters.base import RulesContext, SourceAdapter
from referral_assistant.config import Settings
from referral_assistant.models import Opportunity

try:
    import praw
except ImportError:  # pragma: no cover - optional runtime dependency
    praw = None


REDDIT_BASE_URL = "https://www.reddit.com"


@dataclass(slots=True)
class RedditCandidate:
    submission: Any
    subreddit: Any


class RedditAdapter(SourceAdapter):
    source_name = "reddit"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._rules_cache: dict[str, RulesContext] = {}
        self._reddit = None

    def fetch_candidates(self) -> list[RedditCandidate]:
        client = self._client()
        if not self.settings.subreddits:
            return []

        candidates: list[RedditCandidate] = []
        seen_ids: set[str] = set()
        for subreddit_name in self.settings.subreddits:
            subreddit = client.subreddit(subreddit_name)
            for stream_name, limit in (
                ("hot", self.settings.reddit_hot_limit),
                ("new", self.settings.reddit_new_limit),
            ):
                generator = getattr(subreddit, stream_name)(limit=limit)
                for submission in generator:
                    if submission.id in seen_ids:
                        continue
                    seen_ids.add(submission.id)
                    candidates.append(
                        RedditCandidate(submission=submission, subreddit=subreddit)
                    )
        return candidates

    def fetch_rules_context(self, candidate: RedditCandidate) -> RulesContext:
        community = candidate.subreddit.display_name
        if community in self._rules_cache:
            return self._rules_cache[community]

        parts: list[str] = []
        sources: list[str] = []
        subreddit = candidate.subreddit

        public_description = getattr(subreddit, "public_description", "") or ""
        if public_description:
            parts.append(f"[public_description]\n{public_description}")
            sources.append("public_description")

        sidebar = getattr(subreddit, "description", "") or ""
        if sidebar:
            parts.append(f"[sidebar]\n{sidebar}")
            sources.append("sidebar")

        rules_obj = getattr(subreddit, "rules", None)
        try:
            rules_iterable = rules_obj() if callable(rules_obj) else rules_obj
        except Exception:
            rules_iterable = None
        if rules_iterable:
            lines = []
            for rule in rules_iterable:
                short_name = getattr(rule, "short_name", "") or ""
                description = getattr(rule, "description", "") or ""
                if short_name or description:
                    lines.append(f"{short_name}: {description}".strip(": "))
            if lines:
                parts.append("[rules]\n" + "\n".join(lines))
                sources.append("rules")

        for sticky_number in (1, 2):
            try:
                sticky = subreddit.sticky(number=sticky_number)
            except Exception:
                sticky = None
            if sticky is None:
                continue
            sticky_text = "\n".join(
                [getattr(sticky, "title", "") or "", getattr(sticky, "selftext", "") or ""]
            ).strip()
            if sticky_text:
                parts.append(f"[sticky_{sticky_number}]\n{sticky_text}")
                sources.append(f"sticky_{sticky_number}")

        context = RulesContext(
            community_name=community,
            rules_text="\n\n".join(parts).strip(),
            sources=sources,
        )
        self._rules_cache[community] = context
        return context

    def normalize(self, candidate: RedditCandidate) -> Opportunity:
        submission = candidate.submission
        permalink = getattr(submission, "permalink", "") or ""
        source_url = (
            f"{REDDIT_BASE_URL}{permalink}" if permalink else getattr(submission, "url", "")
        )
        metadata = {
            "permalink": source_url,
            "external_url": getattr(submission, "url", "") or "",
            "score": int(getattr(submission, "score", 0) or 0),
            "num_comments": int(getattr(submission, "num_comments", 0) or 0),
            "is_self": bool(getattr(submission, "is_self", False)),
            "stickied": bool(getattr(submission, "stickied", False)),
        }
        return Opportunity(
            source=self.source_name,
            source_item_id=str(submission.id),
            source_url=source_url,
            community_name=candidate.subreddit.display_name,
            author_name=getattr(getattr(submission, "author", None), "name", "[deleted]"),
            title=getattr(submission, "title", "") or "",
            body=getattr(submission, "selftext", "") or "",
            created_at=datetime.fromtimestamp(
                float(getattr(submission, "created_utc", 0.0)),
                tz=timezone.utc,
            ),
            thread_metadata=metadata,
        )

    def build_open_url(self, opportunity: Opportunity) -> str:
        return opportunity.source_url

    def supports_manual_publish(self) -> bool:
        return True

    def _client(self) -> Any:
        if self._reddit is not None:
            return self._reddit
        if praw is None:
            raise RuntimeError("praw is not installed in the current environment.")
        if not self.settings.reddit_client_id or not self.settings.reddit_client_secret:
            raise RuntimeError("Reddit API credentials are missing.")
        self._reddit = praw.Reddit(
            client_id=self.settings.reddit_client_id,
            client_secret=self.settings.reddit_client_secret,
            user_agent=self.settings.reddit_user_agent,
        )
        return self._reddit
