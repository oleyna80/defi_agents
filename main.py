import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from defi_agents.scout.config import ScoutConfig
from defi_agents.scout.defillama_client import DeFiLlamaClient
from defi_agents.scout.scout import YieldScout
from defi_agents.ai.provider import DeepSeekProvider, MockAIService
from defi_agents.l3_manager import L3AnalysisManager
from defi_agents.config import should_allow_mock_fallback
from defi_agents.security.auditor import SecurityAuditor
from defi_agents.security.defi_client import DeFiClient
from defi_agents.security.goplus_client import GoPlusClient
from defi_agents.security.whitelist import WhitelistProvider
from defi_agents.notifier import TelegramNotifier
from defi_agents.history import save_to_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Sentinel")
# Prevent accidental secret leaks in verbose HTTP request logs (e.g., Telegram bot token in URL path).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _load_env_file(path: str = ".env") -> None:
    env_path = ROOT / path
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Standard KEY=VALUE
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
            continue
        # Fallback for non-standard "<value> #KEY_NAME"
        if "#" in line and "=" not in line:
            value, maybe_key = line.split("#", 1)
            key = maybe_key.strip()
            value = value.strip()
            if key and value and key not in os.environ:
                os.environ[key] = value


def _is_excluded_by_l3(tag) -> bool:  # noqa: ANN001
    if tag is None:
        return False
    value = getattr(tag, "value", str(tag))
    return value in {"AI_REJECT", "PENDING"}


async def run_sentinel_cycle() -> None:
    _load_env_file()
    config = ScoutConfig.from_file("docs/memory-bank/scout_config.json")

    sem = asyncio.Semaphore(3)
    whitelist = WhitelistProvider()
    goplus = GoPlusClient(semaphore=sem)
    defi = DeFiClient(semaphore=sem)
    auditor = SecurityAuditor(whitelist, goplus, defi)

    client = DeFiLlamaClient(config)
    scout = YieldScout(config, client, auditor)
    try:
        provider = DeepSeekProvider()
        logger.info("DeepSeek provider initialized.")
    except Exception as exc:  # noqa: BLE001
        if should_allow_mock_fallback():
            logger.warning("AI init failed: %s. Falling back to MockAI (dev mode).", exc)
            provider = MockAIService()
        else:
            logger.critical("AI init failed and fallback disabled. Stopping startup.")
            raise RuntimeError("Production AI Init Failure") from exc
    l3_manager = L3AnalysisManager(config=config, provider=provider)
    notifier = TelegramNotifier()

    logger.info("Starting Global Scout Cycle (chains: ALL).")

    try:
        opportunities = await scout.analyze()
        opportunities = await l3_manager.process_batch(opportunities)

        # Save to history (post hard filters + security gate)
        save_to_history(opportunities)

        eligible = [
            opt
            for opt in opportunities
            if not _is_excluded_by_l3(opt.candidate.l3_status)
        ]

        safe_min_score = config.min_final_score
        warn_min_score = getattr(config, "min_warn_score", 2.0)
        min_profit = config.gas_efficiency.effective_min_monthly_profit_usd
        profit_ok = [opt for opt in eligible if opt.net_profit_usd >= min_profit]

        def _sec_status_value(opt) -> str | None:  # noqa: ANN001
            sec = getattr(opt, "security", None)
            status = getattr(sec, "status", None)
            if status is None:
                return None
            return getattr(status, "value", str(status))

        safe_picks = [
            opt for opt in eligible if (_sec_status_value(opt) in {"trusted", "pass"} and opt.score >= safe_min_score)
        ]
        warn_picks = [
            opt for opt in eligible if (_sec_status_value(opt) == "warn" and opt.score >= warn_min_score)
        ]
        for opt in safe_picks:
            opt.metadata["bucket"] = "SAFE"
        for opt in warn_picks:
            reasons = {r.strip() for r in opt.metadata.get("warn_reasons", "").split(",") if r.strip()}
            if opt.metadata.get("lindy_softened") == "true":
                opt.metadata["bucket"] = "LINDY/WARN"
            elif reasons and reasons.issubset({"REPUTATION_UNAVAILABLE"}):
                opt.metadata["bucket"] = "WARN/REPUTATION"
            else:
                opt.metadata["bucket"] = "WARN/SECURITY"

        report_picks = safe_picks + warn_picks
        for opt in report_picks:
            opt.metadata["report_group"] = (
                "ACTIONABLE" if opt.net_profit_usd >= min_profit else "WATCHLIST"
            )
            net_profit_1k = (1000.0 * (opt.net_apy / 100.0) / 12.0) - config.gas_efficiency.monthly_gas_cost_usd
            opt.metadata["net_profit_1k_usd"] = f"{net_profit_1k:.2f}"

        logger.info(
            "Final filters: eligible=%s profit_ok=%s safe=%s warn=%s safe_min_score=%.2f warn_min_score=%.2f min_monthly_profit_usd=%.2f",
            len(eligible),
            len(profit_ok),
            len(safe_picks),
            len(warn_picks),
            safe_min_score,
            warn_min_score,
            min_profit,
        )

        actionable_count = sum(1 for pick in report_picks if pick.metadata.get("report_group") == "ACTIONABLE")
        watchlist_count = sum(1 for pick in report_picks if pick.metadata.get("report_group") == "WATCHLIST")
        # Report both actionable and watchlist sections with clear labels.
        if report_picks:
            await notifier.send_alpha_report(report_picks)
            logger.info(
                "Reported %s opportunities (safe=%s warn=%s actionable=%s watchlist=%s).",
                len(report_picks),
                len(safe_picks),
                len(warn_picks),
                actionable_count,
                watchlist_count,
            )
        else:
            logger.info("Match not found. High security standards met.")

    except Exception as exc:  # noqa: BLE001
        logger.exception("Sentinel cycle failed: %s", exc)
        await notifier.send_error(f"Sentinel System Error: {exc}")
        raise


if __name__ == "__main__":
    try:
        asyncio.run(run_sentinel_cycle())
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.critical("FATAL: Process crashed: %s", exc, exc_info=True)
        sys.exit(1)
