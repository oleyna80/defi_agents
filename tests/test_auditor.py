import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.security.auditor import SecurityAuditor
from defi_agents.security.defi_client import DeFiClient
from defi_agents.security.goplus_client import GoPlusClient
from defi_agents.security.models import SecurityReputation, SecurityResult, SecurityStatus
from defi_agents.security.whitelist import WhitelistProvider


class _MockWhitelist(WhitelistProvider):
    def __init__(self, result: SecurityResult | None):
        self._result = result

    def check(self, address: str, chain_id: str):  # noqa: ANN001
        return self._result


class _MockGoPlus(GoPlusClient):
    def __init__(self, result: SecurityResult):
        self._result = result

    async def scan(self, address: str, chain_id: str) -> SecurityResult:
        return self._result


class _MockDeFi(DeFiClient):
    def __init__(self, reputation: SecurityReputation):
        self._reputation = reputation

    async def get_reputation(self, address: str) -> SecurityReputation:
        return self._reputation


def _run(coro):
    import asyncio

    return asyncio.run(coro)


def test_case_honeypot_block_short_circuit():
    tech = SecurityResult(
        status=SecurityStatus.BLOCK,
        score=0,
        reasons=[],
        sources=[],
        is_trusted=False,
        ttl_seconds=3600,
    )
    auditor = SecurityAuditor(
        whitelist_provider=_MockWhitelist(None),
        goplus_client=_MockGoPlus(tech),
        defi_client=_MockDeFi(SecurityReputation()),
    )
    result = _run(auditor.evaluate("0xdead", "1"))
    assert result.status == SecurityStatus.BLOCK


def test_case_old_rekt_amnesty_warn():
    from datetime import datetime, timezone

    reputation = SecurityReputation(
        rekt_history=True,
        has_tier_a_audit=True,
        has_top_tier_audit=True,
        protocol_name="Curve",
    )
    reputation.last_rekt_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    reputation.last_top_tier_audit_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    tech = SecurityResult(
        status=SecurityStatus.PASS,
        score=80,
        reasons=[],
        sources=[],
        is_trusted=False,
        ttl_seconds=3600,
    )
    auditor = SecurityAuditor(
        whitelist_provider=_MockWhitelist(None),
        goplus_client=_MockGoPlus(tech),
        defi_client=_MockDeFi(reputation),
    )
    result = _run(auditor.evaluate("0xcrv", "1"))
    assert result.status in {SecurityStatus.WARN, SecurityStatus.PASS}
    assert any(r.code == "PROTOCOL_REKT_HISTORY_AMNESTY" for r in result.reasons)


def test_case_unidentified_block_fail_safe():
    reputation = SecurityReputation(
        protocol_slug=None,
        protocol_name=None,
        rekt_history=None,
        has_top_tier_audit=None,
        protocol_score=80,
    )
    tech = SecurityResult(
        status=SecurityStatus.PASS,
        score=80,
        reasons=[],
        sources=[],
        is_trusted=False,
        ttl_seconds=3600,
    )
    auditor = SecurityAuditor(
        whitelist_provider=_MockWhitelist(None),
        goplus_client=_MockGoPlus(tech),
        defi_client=_MockDeFi(reputation),
    )
    result = _run(auditor.evaluate("0xunknown", "1"))
    assert result.status == SecurityStatus.BLOCK


def test_case_tier_b_only_pass():
    reputation = SecurityReputation(
        auditors=["Consensys Diligence", "Nethermind"],
        has_tier_b_audit=True,
        is_audited=True,
        protocol_score=85,
        protocol_name="Example Protocol",
        protocol_slug="example-protocol",
    )
    tech = SecurityResult(
        status=SecurityStatus.PASS,
        score=80,
        reasons=[],
        sources=[],
        is_trusted=False,
        ttl_seconds=3600,
    )
    auditor = SecurityAuditor(
        whitelist_provider=_MockWhitelist(None),
        goplus_client=_MockGoPlus(tech),
        defi_client=_MockDeFi(reputation),
    )
    result = _run(auditor.evaluate("0xtierb", "1"))
    assert result.status == SecurityStatus.PASS
    assert any(r.code == "TIER_B_AUDIT_ONLY" for r in result.reasons)


def test_case_certik_only_warn():
    reputation = SecurityReputation(
        auditors=["CertiK"],
        has_low_reputation_audit=True,
        is_audited=True,
        protocol_score=75,
        protocol_name="Example Protocol",
    )
    tech = SecurityResult(
        status=SecurityStatus.PASS,
        score=80,
        reasons=[],
        sources=[],
        is_trusted=False,
        ttl_seconds=3600,
    )
    auditor = SecurityAuditor(
        whitelist_provider=_MockWhitelist(None),
        goplus_client=_MockGoPlus(tech),
        defi_client=_MockDeFi(reputation),
    )
    result = _run(auditor.evaluate("0xcertik", "1"))
    assert result.status == SecurityStatus.WARN
    assert any(r.code == "LOW_REPUTATION_AUDITOR" for r in result.reasons)


def test_case_no_audits_warn():
    reputation = SecurityReputation(
        auditors=[],
        is_audited=False,
        protocol_score=60,
        protocol_name="Example Protocol",
    )
    tech = SecurityResult(
        status=SecurityStatus.PASS,
        score=80,
        reasons=[],
        sources=[],
        is_trusted=False,
        ttl_seconds=3600,
    )
    auditor = SecurityAuditor(
        whitelist_provider=_MockWhitelist(None),
        goplus_client=_MockGoPlus(tech),
        defi_client=_MockDeFi(reputation),
    )
    result = _run(auditor.evaluate("0xnoaudit", "1"))
    assert result.status == SecurityStatus.WARN
    assert any(r.code == "NO_AUDITS_FOUND" for r in result.reasons)


def test_case_whitelist_trusted_fast_track():
    trusted = SecurityResult.trusted_from_whitelist(reason="Whitelist match")
    auditor = SecurityAuditor(
        whitelist_provider=_MockWhitelist(trusted),
        goplus_client=_MockGoPlus(SecurityResult.pass_as_tier1()),
        defi_client=_MockDeFi(SecurityReputation()),
    )
    result = _run(auditor.evaluate("0xeurc", "1"))
    assert result.status == SecurityStatus.TRUSTED
    assert result.is_trusted is True
