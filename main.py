import asyncio
import logging
import os
import sys
from pathlib import Path
from time import time

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
from defi_agents.cache import CacheController
from defi_agents.freshness import FreshnessManager, apply_freshness_policy
from defi_agents.history import save_to_history
from defi_agents.strategy_sim.engine import StrategySimEngine
from defi_agents.strategy_sim.models import SimulationCounters

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


def _telegram_digest_due(config: ScoutConfig) -> tuple[bool, int, int]:
    interval = int(getattr(getattr(config, "reporting", None), "telegram_digest_interval_seconds", 0) or 0)
    if interval <= 0:
        return True, 0, 0
    cache = CacheController(namespace="telegram_digest")
    last_sent = cache.get("last_sent_at")
    now = int(time())
    try:
        last = int(float(last_sent)) if last_sent is not None else 0
    except (TypeError, ValueError):
        last = 0
    if last <= 0:
        return True, interval, 0
    elapsed = now - last
    remaining = max(0, interval - elapsed)
    return elapsed >= interval, interval, remaining


def _mark_telegram_digest_sent() -> None:
    cache = CacheController(namespace="telegram_digest")
    # Keep marker for a long time; it's overwritten on each successful send.
    cache.set("last_sent_at", int(time()), ttl_seconds=365 * 24 * 3600)


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
    turnover_snapshot = None
    directional_snapshot = None
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
    notifier = TelegramNotifier(
        include_tags=config.risk_policy.include_tags_in_report,
        top_n_per_section=getattr(config.reporting, "telegram_top_n_per_section", 0),
        show_source_confidence=getattr(config.reporting, "telegram_show_source_confidence", True),
    )

    logger.info("Starting Global Scout Cycle (chains: ALL).")

    try:
        if getattr(config.reporting, "telegram_directional_sections_enabled", False):
            try:
                directional_snapshot = await client.get_directional_snapshot()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Directional snapshot fetch failed: %s", exc.__class__.__name__)
                directional_snapshot = None
        if getattr(config.reporting, "telegram_turnover_section_enabled", False):
            try:
                turnover_snapshot = await client.get_turnover_snapshot()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Turnover snapshot fetch failed: %s", exc.__class__.__name__)
                turnover_snapshot = None
        opportunities = await scout.analyze()
        dex_stats = getattr(scout, "last_discovery_stats", None)
        if dex_stats is not None:
            logger.info(
                "DEX discovery: llama=%s uniswap_new=%s filtered=%s errors=%s timeouts=%s total=%s enabled=%s",
                dex_stats.dex_llama_count,
                dex_stats.dex_uniswap_new_count,
                dex_stats.dex_filtered_count,
                dex_stats.dex_error_count,
                dex_stats.dex_timeout_count,
                dex_stats.dex_discovery_total,
                config.dex_discovery.uniswap_v3_new_pools.enabled,
            )
        lending_snapshot = getattr(scout, "last_lending_snapshot", None)
        if lending_snapshot is not None and lending_snapshot.has_any():
            eth_supply = (
                f"{lending_snapshot.best_eth_supply.metric_value_pct:.2f}%"
                if lending_snapshot.best_eth_supply
                else "n/a"
            )
            btc_supply = (
                f"{lending_snapshot.best_btc_supply.metric_value_pct:.2f}%"
                if lending_snapshot.best_btc_supply
                else "n/a"
            )
            gho_supply = (
                f"{lending_snapshot.best_gho_supply.metric_value_pct:.2f}%"
                if lending_snapshot.best_gho_supply
                else "n/a"
            )
            stable_borrow = (
                f"{lending_snapshot.lowest_stable_borrow.metric_value_pct:.2f}%"
                if lending_snapshot.lowest_stable_borrow
                else "n/a"
            )
            eurc_borrow = (
                f"{lending_snapshot.lowest_eurc_borrow.metric_value_pct:.2f}%"
                if lending_snapshot.lowest_eurc_borrow
                else "n/a"
            )
            usdc_borrow = (
                f"{lending_snapshot.lowest_usdc_borrow.metric_value_pct:.2f}%"
                if lending_snapshot.lowest_usdc_borrow
                else "n/a"
            )
            logger.info(
                "Lending snapshot: best_eth_supply=%s best_btc_supply=%s best_gho_supply=%s "
                "lowest_stable_borrow=%s lowest_eurc_borrow=%s lowest_usdc_borrow=%s",
                eth_supply,
                btc_supply,
                gho_supply,
                stable_borrow,
                eurc_borrow,
                usdc_borrow,
            )
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
            # Phase A wiring: re-check metadata fields are present before adapters are integrated.
            opt.metadata.setdefault("freshness_status", "UNVERIFIED")
            opt.metadata.setdefault("freshness_provider", "none")
            opt.metadata.setdefault("source_timestamp", "")
            opt.metadata.setdefault("age_minutes", "")
            opt.metadata.setdefault("staleness_score", "")
            opt.metadata.setdefault("apy_divergence_pct", "")
            opt.metadata.setdefault("tvl_divergence_pct", "")

        if config.freshness.recheck_enabled and report_picks:
            freshness_manager = FreshnessManager(config.freshness)
            await freshness_manager.recheck(report_picks)

        freshness_counts = apply_freshness_policy(report_picks, config.freshness)

        # --- Strategy Simulation (v1) ---
        sim_counters = SimulationCounters()
        if config.strategy_sim.enabled and report_picks:
            engine = StrategySimEngine(config)
            # Simulate each candidate and attach metadata
            for pick in report_picks:
                sim_result = engine.simulate_one(pick)
                pick.metadata.update(sim_result.to_metadata_dict())
                # Update counters
                sim_counters.simulated_count += 1
                if sim_result.status.value == "OK":
                    sim_counters.ok_count += 1
                elif sim_result.status.value == "PARTIAL":
                    sim_counters.partial_count += 1
                elif sim_result.status.value == "UNSUPPORTED":
                    sim_counters.unsupported_count += 1
                if sim_result.best_strategy:
                    strat_key = sim_result.best_strategy.value
                    sim_counters.best_strategy_distribution[strat_key] = (
                        sim_counters.best_strategy_distribution.get(strat_key, 0) + 1
                    )
            # Apply policy gates (downgrade to WATCHLIST)
            sim_counters = engine.apply_policy(report_picks, sim_counters)
            logger.info(sim_counters.to_log_line())
        else:
            logger.info("StrategySim disabled or no candidates.")

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
        logger.info(
            "Freshness summary: rechecked=%s fresh=%s stale=%s unverified=%s diverged=%s downgraded=%s "
            "aave_checked=%s aave_ok=%s aave_timeout=%s aave_error=%s aave_schema_mismatch=%s aave_addr_mismatch=%s "
            "recheck_enabled=%s strict=%s",
            freshness_counts["rechecked_count"],
            freshness_counts["fresh_count"],
            freshness_counts["stale_count"],
            freshness_counts["unverified_count"],
            freshness_counts["diverged_count"],
            freshness_counts["downgraded_to_watchlist_count"],
            freshness_counts["aave_checked_count"],
            freshness_counts["aave_ok_count"],
            freshness_counts["aave_timeout_count"],
            freshness_counts["aave_error_count"],
            freshness_counts["aave_schema_mismatch_count"],
            freshness_counts["aave_addr_mismatch_count"],
            config.freshness.recheck_enabled,
            config.freshness.enforce_freshness_for_actionable,
        )
        # Report both actionable and watchlist sections with clear labels.
        if report_picks:
            due, interval, remaining = _telegram_digest_due(config)
            if due:
                await notifier.send_alpha_report(
                    report_picks,
                    lending_snapshot=lending_snapshot,
                    turnover_snapshot=turnover_snapshot,
                    directional_snapshot=directional_snapshot,
                )
                _mark_telegram_digest_sent()
                logger.info(
                    "Reported %s opportunities (safe=%s warn=%s actionable=%s watchlist=%s).",
                    len(report_picks),
                    len(safe_picks),
                    len(warn_picks),
                    actionable_count,
                    watchlist_count,
                )
            else:
                logger.info(
                    "Report suppressed by digest schedule: interval=%ss next_in=%ss picks=%s (actionable=%s watchlist=%s).",
                    interval,
                    remaining,
                    len(report_picks),
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
