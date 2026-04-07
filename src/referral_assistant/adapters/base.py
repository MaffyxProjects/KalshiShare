from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from referral_assistant.models import Opportunity


@dataclass(slots=True)
class RulesContext:
    community_name: str
    rules_text: str
    sources: list[str]


class SourceAdapter(ABC):
    source_name: str

    @abstractmethod
    def fetch_candidates(self) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def fetch_rules_context(self, candidate: Any) -> RulesContext:
        raise NotImplementedError

    @abstractmethod
    def normalize(self, candidate: Any) -> Opportunity:
        raise NotImplementedError

    @abstractmethod
    def build_open_url(self, opportunity: Opportunity) -> str:
        raise NotImplementedError

    @abstractmethod
    def supports_manual_publish(self) -> bool:
        raise NotImplementedError
