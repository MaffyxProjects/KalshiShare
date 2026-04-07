from __future__ import annotations

from dataclasses import dataclass
import time

import requests

from referral_assistant.models import AlertEvent


@dataclass(slots=True)
class DiscordWebhookNotifier:
    webhook_url: str
    timeout_seconds: int = 10
    max_attempts: int = 3

    def send(self, event: AlertEvent) -> bool:
        if not self.webhook_url:
            return False

        payload = {
            "username": "Referral Draft Assistant",
            "content": self._format_message(event),
        }

        response = None
        for attempt in range(1, self.max_attempts + 1):
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout_seconds,
            )
            if response.ok:
                return True
            if attempt < self.max_attempts:
                time.sleep(attempt)

        assert response is not None
        response.raise_for_status()
        return False

    def _format_message(self, event: AlertEvent) -> str:
        metadata_lines = [
            f"- {key}: {value}" for key, value in sorted(event.metadata.items())
        ]
        metadata_text = "\n".join(metadata_lines)
        if metadata_text:
            return (
                f"[{event.level.value.upper()}] {event.event_type}\n"
                f"{event.message}\n{metadata_text}"
            )
        return f"[{event.level.value.upper()}] {event.event_type}\n{event.message}"
