from __future__ import annotations

import asyncio
import hashlib
import random
import time
from urllib.parse import urlparse

from .ai.extractor import ContentExtractor, ExtractionResult
from .ai.provider import AIService, DeepSeekProvider, MockAIService
from .cache import CacheController
from .config import (
    EXTRACTOR_VERSION,
    L3_ANALYSIS_CACHE_TTL_SECONDS,
    L3_CONTENT_CACHE_TTL_SECONDS,
    L3_POLICY_VERSION,
    should_allow_mock_fallback,
)
from .scout.config import ScoutConfig
from .scout.models import FinalTag, L3Judgment, L3Metadata, L3Result, ReasonCode, ScoutResult
from .security.models import SecurityStatus


class L3AnalysisManager:
    def __init__(
        self,
        *,
        config: ScoutConfig,
        provider: AIService | None = None,
        extractor: ContentExtractor | None = None,
        content_cache: CacheController | None = None,
        analysis_cache: CacheController | None = None,
    ) -> None:
        self.config = config
        self.provider = provider or self._default_provider()
        self.extractor = extractor or ContentExtractor()
        self.content_cache = content_cache or CacheController(namespace="l3_content")
        self.analysis_cache = analysis_cache or CacheController(namespace="l3_audit")
        self._domain_last_request: dict[str, float] = {}

    def _default_provider(self) -> AIService:
        try:
            return DeepSeekProvider()
        except Exception as exc:  # noqa: BLE001
            if should_allow_mock_fallback():
                return MockAIService()
            raise RuntimeError(
                "L3Manager: failed to initialize DeepSeek provider and mock fallback is disabled."
            ) from exc

    async def process_batch(self, results: list[ScoutResult]) -> list[ScoutResult]:
        ranked = sorted(results, key=lambda r: r.score, reverse=True)
        processed = 0
        for result in ranked:
            if processed >= self.config.l3_max_audits_per_cycle:
                break
            if not self._is_eligible(result):
                continue

            extraction, cache_hit_content = await self._get_content(result)
            l3_result, cache_hit_analysis = await self._get_analysis(
                result=result,
                extraction=extraction,
                cache_hit_content=cache_hit_content,
            )
            if l3_result.metadata:
                l3_result.metadata.cache_hit_content = cache_hit_content
                l3_result.metadata.cache_hit_analysis = cache_hit_analysis
            self._apply_policy(result, l3_result)
            processed += 1
        return results

    def _is_eligible(self, result: ScoutResult) -> bool:
        candidate = result.candidate
        if not candidate.address or not candidate.chain_id:
            return False
        if not result.security:
            return False
        if result.security.status not in {SecurityStatus.TRUSTED, SecurityStatus.PASS}:
            return False

        is_new = candidate.contract_age_days is not None and candidate.contract_age_days < 30
        apy_anomaly = (
            candidate.apy_mean_30d is not None
            and candidate.apy_mean_30d > 0
            and candidate.apy / candidate.apy_mean_30d >= self.config.apy_anomaly_ratio
        )
        is_anomalous = candidate.yield_quality < self.config.yield_quality_min or apy_anomaly
        return is_new or is_anomalous

    async def _get_content(self, result: ScoutResult) -> tuple[ExtractionResult, bool]:
        candidate = result.candidate
        if not candidate.project_url:
            return ExtractionResult(
                text="",
                source="none",
                reason_code=ReasonCode.NO_DATA,
                content_hash=hashlib.sha256(b"").hexdigest(),
            ), False

        url = candidate.project_url.strip()
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cached = self.content_cache.get(key)
        if cached is not None:
            return ExtractionResult(**cached), True

        await self._throttle_domain(url)
        extraction = await self.extractor.extract(url)
        self.content_cache.set(
            key,
            {
                "text": extraction.text,
                "source": extraction.source,
                "reason_code": extraction.reason_code.value if extraction.reason_code else None,
                "content_hash": extraction.content_hash,
            },
            ttl_seconds=L3_CONTENT_CACHE_TTL_SECONDS,
        )
        return extraction, False

    async def _get_analysis(
        self,
        *,
        result: ScoutResult,
        extraction: ExtractionResult,
        cache_hit_content: bool,
    ) -> tuple[L3Result, bool]:
        key = self._analysis_cache_key(result, extraction.content_hash)
        cached = self.analysis_cache.get(key)
        if cached is not None:
            parsed = L3Result.model_validate(cached)
            if parsed.metadata:
                parsed.metadata.cache_hit_analysis = True
            return parsed, True

        reason = extraction.reason_code
        parsed_reason = None
        if reason:
            parsed_reason = reason if isinstance(reason, ReasonCode) else ReasonCode(reason)
        l3_result = await self.provider.analyze(
            candidate=result.candidate,
            security_status=result.security.status,
            docs_text=extraction.text,
            extraction_source=extraction.source,
            extraction_reason=parsed_reason,
            cache_hit_content=cache_hit_content,
            cache_hit_analysis=False,
        )

        if not l3_result.metadata:
            l3_result.metadata = L3Metadata(
                provider=getattr(self.provider, "provider_name", "unknown"),
                model=getattr(self.provider, "model", "unknown"),
                prompt_version=getattr(self.provider, "prompt_version", "v1.1"),
                extractor_version=EXTRACTOR_VERSION,
                policy_version=L3_POLICY_VERSION,
                extraction_source=extraction.source,
                cache_hit_content=cache_hit_content,
                cache_hit_analysis=False,
            )
        self.analysis_cache.set(
            key,
            l3_result.model_dump(mode="json"),
            ttl_seconds=L3_ANALYSIS_CACHE_TTL_SECONDS,
        )
        return l3_result, False

    def _analysis_cache_key(self, result: ScoutResult, content_hash: str) -> str:
        candidate = result.candidate
        provider = getattr(self.provider, "provider_name", "unknown")
        model = getattr(self.provider, "model", "unknown")
        prompt_version = getattr(self.provider, "prompt_version", "v1.1")
        raw = (
            f"{candidate.chain_id}:{candidate.address}:{content_hash}:"
            f"{provider}:{model}:{prompt_version}:{EXTRACTOR_VERSION}:{L3_POLICY_VERSION}"
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _throttle_domain(self, url: str) -> None:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            return
        now = time.monotonic()
        previous = self._domain_last_request.get(host)
        if previous is not None and (now - previous) < 5.0:
            await asyncio.sleep(random.uniform(1.0, 3.0))
        self._domain_last_request[host] = time.monotonic()

    def _apply_policy(self, result: ScoutResult, l3_result: L3Result) -> None:
        candidate = result.candidate
        candidate.l3_data = l3_result
        reasons = set(l3_result.reason_codes)
        judgment = l3_result.judgment
        confidence = l3_result.confidence

        final_tag = FinalTag.PENDING
        k_ai = 0.5

        if judgment == L3Judgment.ERROR:
            if reasons & {ReasonCode.SSRF_BLOCKED, ReasonCode.JSON_PARSE_FAIL, ReasonCode.RATE_LIMIT_HIT}:
                final_tag = FinalTag.AUDIT_LAG
            else:
                final_tag = FinalTag.AUDIT_LAG
        elif judgment == L3Judgment.INCONCLUSIVE:
            if ReasonCode.PDF_UNSUPPORTED in reasons:
                final_tag = FinalTag.AUDIT_LAG
            elif reasons & {ReasonCode.NO_DATA, ReasonCode.EXTRACTION_FAILED}:
                final_tag = FinalTag.PENDING
            else:
                final_tag = FinalTag.PENDING
        elif judgment == L3Judgment.PASS:
            if confidence >= self.config.l3_pass_confidence_threshold:
                final_tag = FinalTag.ALPHA_STABLE
                k_ai = 1.0
            else:
                final_tag = FinalTag.PENDING
        elif judgment == L3Judgment.WARN:
            if confidence >= self.config.l3_warn_confidence_threshold:
                final_tag = FinalTag.SOLID_RISK
                k_ai = max(0.0, 1.0 - (0.4 * confidence))
            else:
                final_tag = FinalTag.PENDING
        elif judgment == L3Judgment.HIGH_RISK:
            if confidence >= self.config.l3_high_risk_confidence_threshold:
                final_tag = FinalTag.AI_REJECT
                k_ai = 0.0
            else:
                final_tag = FinalTag.AI_DOUBT
                k_ai = 0.3

        candidate.ai_security_factor = k_ai
        candidate.l3_status = final_tag
        result.score = result.score * k_ai
        result.metadata["l3_tag"] = final_tag.value
        result.metadata["l3_confidence"] = f"{confidence:.3f}"
        result.metadata["l3_reason_codes"] = ",".join(code.value for code in l3_result.reason_codes)
