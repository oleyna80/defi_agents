import pytest


def test_aggregate_reputation_unavailable_is_warn_only():
    from defi_agents.security.models import SecurityReputation, SecurityResult, SecurityStatus

    res = SecurityResult(status=SecurityStatus.PASS, score=80)
    res.aggregate_reputation(SecurityReputation.unavailable())

    assert res.status == SecurityStatus.WARN
    codes = [r.code for r in res.reasons]
    assert "REPUTATION_UNAVAILABLE" in codes
    assert "NO_AUDITS_FOUND" not in codes


@pytest.mark.asyncio
async def test_auditor_does_not_block_when_reputation_adapter_fails():
    from defi_agents.security.auditor import SecurityAuditor
    from defi_agents.security.models import SecurityResult, SecurityStatus

    class _Whitelist:
        def check(self, address: str, chain_id: str):  # noqa: ANN001
            return None

    class _GoPlus:
        async def scan(self, address: str, chain_id: str):  # noqa: ANN001
            return SecurityResult(status=SecurityStatus.PASS, score=80)

    class _DeFi:
        async def get_reputation(self, address: str):  # noqa: ANN001
            raise RuntimeError("boom")

    auditor = SecurityAuditor(_Whitelist(), _GoPlus(), _DeFi())
    out = await auditor.evaluate("0x0000000000000000000000000000000000000001", "1")
    assert out.status in {SecurityStatus.PASS, SecurityStatus.WARN}
    assert any(r.code == "REPUTATION_UNAVAILABLE" for r in out.reasons)

