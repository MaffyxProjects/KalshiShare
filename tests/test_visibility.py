from types import SimpleNamespace

from referral_assistant.models import VisibilityStatus
from referral_assistant.services.visibility import VisibilityVerifier


def test_verify_visibility_detects_visible_content(monkeypatch) -> None:
    verifier = VisibilityVerifier()

    def fake_get(*args, **kwargs):
        return SimpleNamespace(status_code=200, text="hello expected snippet world")

    monkeypatch.setattr("referral_assistant.services.visibility.requests.get", fake_get)

    result = verifier.verify_visibility(
        lead_id=1,
        public_url="https://example.com/thread",
        expected_snippet="expected snippet",
    )

    assert result.status == VisibilityStatus.VISIBLE


def test_verify_visibility_detects_removed_content(monkeypatch) -> None:
    verifier = VisibilityVerifier()

    def fake_get(*args, **kwargs):
        return SimpleNamespace(status_code=200, text="this comment has been removed")

    monkeypatch.setattr("referral_assistant.services.visibility.requests.get", fake_get)

    result = verifier.verify_visibility(
        lead_id=1,
        public_url="https://example.com/thread",
        expected_snippet="expected snippet",
    )

    assert result.status == VisibilityStatus.NOT_VISIBLE
