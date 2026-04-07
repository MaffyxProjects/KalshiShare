from __future__ import annotations

from datetime import datetime, timezone

from referral_assistant.models import (
    ComplianceEvidence,
    ComplianceStatus,
    DraftRecord,
    DraftStatus,
    GeminiDecision,
    Opportunity,
    Persona,
)
from referral_assistant.runtime import create_app_context
from referral_assistant.ui import dashboard as dashboard_ui


def _insert_record(context) -> int:
    opportunity = Opportunity(
        source="reddit",
        source_item_id="abc123",
        source_url="https://example.com/thread",
        community_name="beermoney",
        author_name="tester",
        title="Kalshi referral thread",
        body="Prediction markets and passive income",
        created_at=datetime.now(timezone.utc),
        thread_metadata={"score": 5, "num_comments": 3},
    )
    compliance = ComplianceEvidence(
        status=ComplianceStatus.ALLOWED,
        reason_codes=["rules_allow_referrals"],
        summary="Rules explicitly allow referral content.",
        evidence_lines=["Referral links are allowed in this thread."],
        allow_matches=["Referral links are allowed in this thread."],
    )
    decision = GeminiDecision(
        eligible=True,
        reason_codes=["rules_allow_referrals"],
        chosen_persona=Persona.HUNTER,
        disclosure_required=True,
        reply_text="{{disclosure_line}}\n\nUse {{referral_link}}",
        confidence=0.9,
        rationale="Good fit.",
    )
    record = DraftRecord(
        opportunity=opportunity,
        compliance=compliance,
        decision=decision,
        status=DraftStatus.QUEUED_FOR_MANUAL_REVIEW,
    )
    return context.database.save_draft_record(record, score=42.0)


def test_flask_dashboard_overview_loads(tmp_path, monkeypatch) -> None:
    context = create_app_context(root_dir=tmp_path)
    monkeypatch.setattr(dashboard_ui, "_APP_CONTEXT", context)
    app = dashboard_ui.create_flask_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Referral Draft Assistant" in response.data


def test_flask_dashboard_can_dismiss_draft(tmp_path, monkeypatch) -> None:
    context = create_app_context(root_dir=tmp_path)
    lead_id = _insert_record(context)
    monkeypatch.setattr(dashboard_ui, "_APP_CONTEXT", context)
    app = dashboard_ui.create_flask_app()
    client = app.test_client()

    response = client.post(
        f"/draft/{lead_id}/dismiss",
        data={"operator_notes": "not a fit"},
        follow_redirects=False,
    )

    updated = context.database.get_draft_record(lead_id)
    assert response.status_code == 302
    assert updated is not None
    assert updated.status == DraftStatus.DISMISSED
    assert updated.operator_notes == "not a fit"
