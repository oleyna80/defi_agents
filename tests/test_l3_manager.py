import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.ai.extractor import ExtractionResult
from defi_agents.cache import CacheController
from defi_agents.l3_manager import L3AnalysisManager
from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.models import L3Judgment, L3Result, ReasonCode, ScoutCandidate, ScoutResult
from defi_agents.security.models import SecurityResult, SecurityStatus


class _Provider:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = 0
        self.provider_name = "test"
        self.model = "test-model"
        self.prompt_version = "v1.1"

    async def analyze(
        self,
        *,
        candidate,
        security_status,
        docs_text,
        extraction_source,
        extraction_reason,
        cache_hit_content,
        cache_hit_analysis,
    ) -> L3Result:
        self.calls += 1
        return self.mapping[candidate.pool_id]


class _Extractor:
    def __init__(self, reason: ReasonCode | None = None):
        self.reason = reason

    async def extract(self, url: str | None) -> ExtractionResult:
        if self.reason is not None:
            return ExtractionResult(
                text="",
                source="none",
                reason_code=self.reason,
                content_hash="0" * 64,
            )
        return ExtractionResult(
            text="protocol docs text",
            source="jina",
            reason_code=None,
            content_hash="a" * 64,
        )


def _mk_result(pool_id: str, score: float = 20.0) -> ScoutResult:
    candidate = ScoutCandidate.model_validate(
        {
            "pool": pool_id,
            "project": "dex",
            "chain": "Base",
            "chain_id": 8453,
            "symbol": "USDC-USDT",
            "address": "0x" + pool_id[-1] * 40,
            "tvlUsd": 5_000_000,
            "apy": 20.0,
            "apyBase": 12.0,
            "apyReward": 8.0,
            "contract_age_days": 10,
            "url": "https://example.com/docs",
        }
    )
    return ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.PASS, score=90, reasons=[], sources=[]),
        net_apy=16.0,
        score=score,
        net_profit_usd=12.0,
        priority="LOW_VOLATILITY",
    )


def _run(coro):
    return asyncio.run(coro)


def test_l3_pass_high_confidence_keeps_score(tmp_path):
    cfg = ScoutConfig(l3_max_audits_per_cycle=3)
    res = _mk_result("pool1")
    svc = _Provider({"pool1": L3Result(judgment=L3Judgment.PASS, confidence=0.9)})
    mgr = L3AnalysisManager(
        config=cfg,
        provider=svc,
        extractor=_Extractor(),
        content_cache=CacheController("l3_content_test_pass", base_dir=tmp_path),
        analysis_cache=CacheController("l3_test_pass", base_dir=tmp_path),
    )

    _run(mgr.process_batch([res]))

    assert res.candidate.l3_status.value == "ALPHA_STABLE"
    assert res.candidate.ai_security_factor == 1.0
    assert res.score == 20.0


def test_l3_warn_applies_penalty(tmp_path):
    cfg = ScoutConfig(l3_max_audits_per_cycle=3)
    res = _mk_result("pool2")
    svc = _Provider({"pool2": L3Result(judgment=L3Judgment.WARN, confidence=0.9)})
    mgr = L3AnalysisManager(
        config=cfg,
        provider=svc,
        extractor=_Extractor(),
        content_cache=CacheController("l3_content_test_warn", base_dir=tmp_path),
        analysis_cache=CacheController("l3_test_warn", base_dir=tmp_path),
    )

    _run(mgr.process_batch([res]))

    assert res.candidate.l3_status.value == "SOLID_RISK"
    assert round(res.candidate.ai_security_factor, 2) == 0.64
    assert round(res.score, 2) == 12.80


def test_l3_high_risk_rejects(tmp_path):
    cfg = ScoutConfig(l3_max_audits_per_cycle=3)
    res = _mk_result("pool3")
    svc = _Provider({"pool3": L3Result(judgment=L3Judgment.HIGH_RISK, confidence=0.9)})
    mgr = L3AnalysisManager(
        config=cfg,
        provider=svc,
        extractor=_Extractor(),
        content_cache=CacheController("l3_content_test_high_risk", base_dir=tmp_path),
        analysis_cache=CacheController("l3_test_high_risk", base_dir=tmp_path),
    )

    _run(mgr.process_batch([res]))

    assert res.candidate.l3_status.value == "AI_REJECT"
    assert res.candidate.ai_security_factor == 0.0
    assert res.score == 0.0


def test_l3_budget_guardrail_limits_calls(tmp_path):
    cfg = ScoutConfig(l3_max_audits_per_cycle=3)
    results = [_mk_result(f"pool{i}", score=20 - i) for i in range(1, 6)]
    mapping = {r.candidate.pool_id: L3Result(judgment=L3Judgment.PASS, confidence=0.9) for r in results}
    svc = _Provider(mapping)
    mgr = L3AnalysisManager(
        config=cfg,
        provider=svc,
        extractor=_Extractor(),
        content_cache=CacheController("l3_content_test_budget", base_dir=tmp_path),
        analysis_cache=CacheController("l3_test_budget", base_dir=tmp_path),
    )

    _run(mgr.process_batch(results))

    assert svc.calls == 3


def test_l3_error_mapping_to_audit_lag(tmp_path):
    cfg = ScoutConfig(l3_max_audits_per_cycle=1)
    res = _mk_result("pool9")
    svc = _Provider(
        {
            "pool9": L3Result(
                judgment=L3Judgment.ERROR,
                confidence=0.0,
                reason_codes=[ReasonCode.JSON_PARSE_FAIL],
            )
        }
    )
    mgr = L3AnalysisManager(
        config=cfg,
        provider=svc,
        extractor=_Extractor(),
        content_cache=CacheController("l3_content_test_error", base_dir=tmp_path),
        analysis_cache=CacheController("l3_test_error", base_dir=tmp_path),
    )

    _run(mgr.process_batch([res]))

    assert res.candidate.l3_status.value == "AUDIT_LAG"
    assert res.candidate.ai_security_factor == 0.5
