import pytest

from referral_assistant.models import Persona
from referral_assistant.services.gemini_service import GeminiService, GeminiServiceError


def test_parse_response_accepts_valid_json_payload() -> None:
    service = GeminiService(api_key="test-key", model_name="gemini-test")

    result = service.parse_response(
        """
        {
          "eligible": true,
          "reason_codes": ["rules_allow_referrals"],
          "chosen_persona": "Hunter",
          "disclosure_required": true,
          "reply_text": "Try {{disclosure_line}} and {{referral_link}}",
          "confidence": 0.93,
          "rationale": "Good fit for bonus seekers."
        }
        """
    )

    assert result.eligible is True
    assert result.chosen_persona == Persona.HUNTER
    assert result.confidence == 0.93


def test_parse_response_rejects_missing_required_keys() -> None:
    service = GeminiService(api_key="test-key", model_name="gemini-test")

    with pytest.raises(GeminiServiceError):
        service.parse_response('{"eligible": true}')
