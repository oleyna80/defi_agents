from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from defi_agents.ai.provider import DeepSeekProvider
from defi_agents.cache import CacheController
from defi_agents.l3_manager import L3AnalysisManager
from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.models import PriorityTier, ScoutCandidate, ScoutResult
from defi_agents.security.models import SecurityResult, SecurityStatus


async def main() -> None:
    load_dotenv(ROOT / ".env")
    print("Starting live L3 smoke test...")

    if not os.getenv("DEEPSEEK_API_KEY"):
        print("ERROR: DEEPSEEK_API_KEY is missing in .env")
        return

    provider = DeepSeekProvider()
    config = ScoutConfig(l3_max_audits_per_cycle=1)

    # Use separate cache namespaces to avoid false positives from previous runs.
    suffix = str(int(time.time()))
    manager = L3AnalysisManager(
        config=config,
        provider=provider,
        content_cache=CacheController(namespace=f"debug_l3_content_{suffix}"),
        analysis_cache=CacheController(namespace=f"debug_l3_analysis_{suffix}"),
    )

    candidate = ScoutCandidate.model_validate(
        {
            "pool": "debug-ethena-usde",
            "project": "Ethena",
            "chain": "Ethereum",
            "chain_id": 1,
            "symbol": "USDE-USDT",
            "address": "0x4c9edd5852cd905f086c759e8383e097148f6001",
            "url": "https://ethena-labs.gitbook.io/ethena-labs",
            "tvlUsd": 100_000_000,
            "apy": 15.5,
            "apyBase": 10.0,
            "apyReward": 5.5,
            "apyMean30d": 6.0,
            "contract_age_days": 10,
        }
    )

    scout_result = ScoutResult(
        candidate=candidate,
        security=SecurityResult(status=SecurityStatus.PASS, score=90, reasons=[], sources=[]),
        net_apy=12.75,
        score=85.0,
        net_profit_usd=20.0,
        priority=PriorityTier.LOW_VOLATILITY,
    )

    results = await manager.process_batch([scout_result])
    final = results[0].candidate.l3_data
    tag = results[0].candidate.l3_status

    if final is None:
        print("ERROR: no L3 result produced")
        return

    print("Done.")
    print(f"Judgment: {final.judgment.value}")
    print(f"Final Tag: {tag.value if tag else 'N/A'}")
    print(f"Confidence: {final.confidence}")
    print(f"Reason Codes: {[r.value for r in final.reason_codes]}")
    print(f"Rationale: {final.decision_rationale}")
    if final.metadata:
        print(
            "Metadata:",
            {
                "provider": final.metadata.provider,
                "model": final.metadata.model,
                "extraction_source": final.metadata.extraction_source,
                "retry_count": final.metadata.retry_count,
                "latency_ms": round(final.metadata.latency_ms, 2),
                "tokens_input": final.metadata.tokens_input,
                "tokens_output": final.metadata.tokens_output,
            },
        )


if __name__ == "__main__":
    asyncio.run(main())
