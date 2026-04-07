from __future__ import annotations

import json
from typing import Any

from referral_assistant.models import ComplianceEvidence, GeminiDecision, Opportunity, Persona
from referral_assistant.services.manual_review import DISCLOSURE_TOKEN, REFERRAL_LINK_TOKEN

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover - optional runtime dependency
    genai = None


RESPONSE_SCHEMA = {
    "type": "object",
    "required": [
        "eligible",
        "reason_codes",
        "chosen_persona",
        "disclosure_required",
        "reply_text",
        "confidence",
    ],
    "properties": {
        "eligible": {"type": "boolean"},
        "reason_codes": {"type": "array", "items": {"type": "string"}},
        "chosen_persona": {"type": "string", "enum": ["Analyst", "Hunter", "None"]},
        "disclosure_required": {"type": "boolean"},
        "reply_text": {"type": "string"},
        "confidence": {"type": "number"},
        "rationale": {"type": "string"},
    },
}


class GeminiServiceError(RuntimeError):
    pass


class GeminiService:
    def __init__(self, api_key: str, model_name: str) -> None:
        self.api_key = api_key.strip()
        self.model_name = model_name
        self._configured = False

    def decide(
        self,
        opportunity: Opportunity,
        compliance: ComplianceEvidence,
    ) -> GeminiDecision:
        if not compliance.is_allowed:
            return GeminiDecision(
                eligible=False,
                reason_codes=compliance.reason_codes,
                chosen_persona=Persona.NONE,
                disclosure_required=True,
                reply_text="",
                confidence=0.0,
                rationale="Compliance gate did not allow drafting.",
            )

        if not self.api_key:
            raise GeminiServiceError("Gemini API key is missing.")
        if genai is None:
            raise GeminiServiceError(
                "google-generativeai is not installed in the current environment."
            )

        self._configure()
        model = genai.GenerativeModel(self.model_name)
        prompt = self._build_prompt(opportunity, compliance)
        generation_config = self._build_generation_config()

        try:
            response = model.generate_content(
                prompt,
                generation_config=generation_config,
            )
        except Exception as exc:  # pragma: no cover - network dependency
            raise GeminiServiceError(f"Gemini request failed: {exc}") from exc

        response_text = getattr(response, "text", "") or ""
        if not response_text and getattr(response, "candidates", None):
            parts = []
            for candidate in response.candidates:
                content = getattr(candidate, "content", None)
                if not content:
                    continue
                for part in getattr(content, "parts", []):
                    part_text = getattr(part, "text", "")
                    if part_text:
                        parts.append(part_text)
            response_text = "".join(parts)

        return self.parse_response(response_text)

    def parse_response(self, response_text: str) -> GeminiDecision:
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise GeminiServiceError(f"Gemini returned invalid JSON: {exc}") from exc

        missing = [key for key in RESPONSE_SCHEMA["required"] if key not in payload]
        if missing:
            raise GeminiServiceError(
                f"Gemini JSON response is missing required keys: {', '.join(missing)}"
            )

        eligible = bool(payload["eligible"])
        reason_codes = [
            str(value).strip()
            for value in payload.get("reason_codes", [])
            if str(value).strip()
        ]
        persona = _parse_persona(payload.get("chosen_persona"))
        disclosure_required = bool(payload["disclosure_required"])
        reply_text = str(payload.get("reply_text", "")).strip()
        confidence = max(0.0, min(float(payload["confidence"]), 1.0))
        rationale = str(payload.get("rationale", "")).strip()

        if eligible and not reply_text:
            raise GeminiServiceError(
                "Gemini marked a draft eligible but returned empty reply_text."
            )

        return GeminiDecision(
            eligible=eligible,
            reason_codes=reason_codes,
            chosen_persona=persona,
            disclosure_required=disclosure_required,
            reply_text=reply_text,
            confidence=confidence,
            rationale=rationale,
        )

    def _configure(self) -> None:
        if self._configured:
            return
        genai.configure(api_key=self.api_key)
        self._configured = True

    def _build_generation_config(self) -> Any:
        config_kwargs = {
            "temperature": 0.3,
            "response_mime_type": "application/json",
        }
        generation_config_type = getattr(getattr(genai, "types", None), "GenerationConfig", None)
        if generation_config_type is None:
            return config_kwargs
        try:
            return generation_config_type(
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                temperature=0.3,
            )
        except TypeError:
            return generation_config_type(**config_kwargs)

    def _build_prompt(
        self,
        opportunity: Opportunity,
        compliance: ComplianceEvidence,
    ) -> str:
        payload = {
            "opportunity": opportunity.to_dict(),
            "compliance": compliance.to_dict(),
            "personas": {
                "Analyst": "Focus on hedging, market mechanics, risk framing, and prediction market context.",
                "Hunter": "Focus on the sign-up economics, bonus value, and concise ROI framing.",
            },
            "requirements": [
                "Return valid JSON only.",
                "Choose 'None' if the thread is not a good fit even though compliance passed.",
                "Keep reply_text concise, context-aware, and manual-review friendly.",
                f"If eligible is true, include the literal token {REFERRAL_LINK_TOKEN} exactly once.",
                f"If disclosure_required is true, include the literal token {DISCLOSURE_TOKEN}.",
                "Do not promise profits or make unsupported claims.",
                "Avoid aggressive calls to action and avoid sounding automated.",
            ],
        }
        return json.dumps(payload, ensure_ascii=True, indent=2)


def _parse_persona(value: Any) -> Persona:
    normalized = str(value or "").strip().lower()
    if normalized == "analyst":
        return Persona.ANALYST
    if normalized == "hunter":
        return Persona.HUNTER
    return Persona.NONE
