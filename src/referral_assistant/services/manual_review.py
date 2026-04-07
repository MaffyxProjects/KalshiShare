from __future__ import annotations

from dataclasses import dataclass

from referral_assistant.models import DraftRecord


DISCLOSURE_LINE = (
    "Disclosure: this is a referral link and I may receive a bonus if you sign up."
)
REFERRAL_LINK_TOKEN = "{{referral_link}}"
DISCLOSURE_TOKEN = "{{disclosure_line}}"


@dataclass(slots=True)
class ManualPublishPacket:
    lead_id: int | None
    open_url: str
    rendered_reply: str
    disclosure_reminder: str
    persona: str
    source_label: str


class ManualPublishHelper:
    def __init__(self, referral_url: str) -> None:
        self.referral_url = referral_url.strip()

    def prepare(self, record: DraftRecord) -> ManualPublishPacket:
        rendered = record.decision.reply_text.replace(REFERRAL_LINK_TOKEN, self.referral_url)
        disclosure_reminder = ""

        if record.decision.disclosure_required:
            rendered = rendered.replace(DISCLOSURE_TOKEN, DISCLOSURE_LINE)
            if DISCLOSURE_LINE.lower() not in rendered.lower():
                rendered = f"{DISCLOSURE_LINE}\n\n{rendered}".strip()
            disclosure_reminder = DISCLOSURE_LINE
        else:
            rendered = rendered.replace(DISCLOSURE_TOKEN, "")

        if self.referral_url and self.referral_url.lower() not in rendered.lower():
            rendered = f"{rendered}\n\n{self.referral_url}".strip()

        return ManualPublishPacket(
            lead_id=record.id,
            open_url=record.opportunity.source_url,
            rendered_reply=rendered.strip(),
            disclosure_reminder=disclosure_reminder,
            persona=record.decision.chosen_persona.value,
            source_label=f"{record.opportunity.source}:{record.opportunity.community_name}",
        )
