from referral_assistant.adapters.base import RulesContext
from referral_assistant.models import ComplianceStatus
from referral_assistant.services.compliance import ComplianceParser


def test_compliance_parser_allows_explicit_referral_language() -> None:
    parser = ComplianceParser()
    context = RulesContext(
        community_name="beermoney",
        rules_text="Referral links are allowed in weekly bonus threads.",
        sources=["sidebar"],
    )

    result = parser.evaluate(context)

    assert result.status == ComplianceStatus.ALLOWED
    assert "rules_allow_referrals" in result.reason_codes


def test_compliance_parser_blocks_explicit_denials() -> None:
    parser = ComplianceParser()
    context = RulesContext(
        community_name="beermoney",
        rules_text="No referral or affiliate links. Spam will be removed.",
        sources=["rules"],
    )

    result = parser.evaluate(context)

    assert result.status == ComplianceStatus.BLOCKED
    assert "rules_explicitly_block_referrals" in result.reason_codes


def test_compliance_parser_marks_ambiguous_rules_as_blocked_by_default() -> None:
    parser = ComplianceParser()
    context = RulesContext(
        community_name="beermoney",
        rules_text="Be respectful. Low effort posts may be removed.",
        sources=["sticky_1"],
    )

    result = parser.evaluate(context)

    assert result.status == ComplianceStatus.AMBIGUOUS
    assert "rules_ambiguous_blocked_by_default" in result.reason_codes
