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
from defi_agents.freshness import FreshnessManager, apply_confidence_factors, apply_freshness_policy
from defi_agents.history import save_to_history
from defi_agents.shadow_metrics import ShadowMetricsTracker
from defi_agents.strategy_sim.engine import StrategySimEngine
from defi_agents.strategy_sim.models import SimulationCounters
from defi_agents.lp.band_depth import scan_pool_band_depth
from defi_agents.lp.tick_provider import UniswapV3TickProvider
from defi_agents.lp.rpc_helper import fetch_slot0_tick
from defi_agents.lp.models import DataQuality

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


def _telegram_no_opps_heartbeat_due(config: ScoutConfig) -> tuple[bool, int, int]:
    reporting = getattr(config, "reporting", None)
    enabled = bool(getattr(reporting, "telegram_no_opportunities_heartbeat_enabled", False))
    interval = int(getattr(reporting, "telegram_no_opportunities_heartbeat_interval_seconds", 0) or 0)
    if not enabled or interval <= 0:
        return False, interval, 0
    cache = CacheController(namespace="telegram_no_opps_heartbeat")
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


def _mark_telegram_no_opps_heartbeat_sent() -> None:
    cache = CacheController(namespace="telegram_no_opps_heartbeat")
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
        show_market_signals=getattr(config.reporting, "telegram_show_market_signals", False),
        chat_id_env=(
            getattr(config.reporting, "telegram_shadow_chat_id_env", "TELEGRAM_SHADOW_CHAT_ID")
            if getattr(config.reporting, "telegram_shadow_mode_enabled", False)
            else None
        ),
        message_prefix=(
            getattr(config.reporting, "telegram_shadow_prefix", "⚠️ SHADOW — DO NOT ACT")
            if getattr(config.reporting, "telegram_shadow_mode_enabled", False)
            else ""
        ),
    )
    if getattr(config.reporting, "telegram_shadow_mode_enabled", False):
        logger.info(
            "Shadow mode enabled: chat_id_env=%s digest_interval=%ss",
            getattr(config.reporting, "telegram_shadow_chat_id_env", "TELEGRAM_SHADOW_CHAT_ID"),
            int(getattr(config.reporting, "telegram_digest_interval_seconds", 0) or 0),
        )
    shadow_tracker = ShadowMetricsTracker(
        horizon_seconds=int(getattr(config.reporting, "telegram_shadow_metrics_horizon_seconds", 86_400) or 86_400),
        capture_interval_seconds=int(
            getattr(config.reporting, "telegram_shadow_capture_interval_seconds", 21_600) or 21_600
        ),
        retention_seconds=int(getattr(config.reporting, "telegram_shadow_retention_seconds", 1_209_600) or 1_209_600),
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
        provider_stats = getattr(client, "last_provider_counters", {}) or {}
        pools_stats = provider_stats.get("yields_pools", {})
        if pools_stats:
            logger.info(
                "DeFiLlama provider: pools requests=%s success=%s timeouts=%s errors=%s parse_errors=%s cache_hits=%s",
                pools_stats.get("request_count", 0),
                pools_stats.get("success_count", 0),
                pools_stats.get("timeout_count", 0),
                pools_stats.get("error_count", 0),
                pools_stats.get("parse_error_count", 0),
                pools_stats.get("cache_hit_count", 0),
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
        my_pools_report = getattr(scout, "last_my_pools_report", None)
        if config.my_pools_monitor.enabled and my_pools_report is not None:
            logger.info(
                "My Pools monitor: configured=%s snapshots=%s healthy=%s watch=%s unverified=%s",
                len(config.my_pools_monitor.pools),
                len(getattr(my_pools_report, "snapshots", []) or []),
                int(getattr(my_pools_report, "healthy_count", 0) or 0),
                int(getattr(my_pools_report, "watch_count", 0) or 0),
                int(getattr(my_pools_report, "unverified_count", 0) or 0),
            )
        opportunities = await l3_manager.process_batch(opportunities)

        # Save to history (post hard filters + security gate)
        save_to_history(opportunities)

        # --- Tick Density Band Depth Scan (Phase A output-hook) ---
        td_cfg = config.tick_density
        td_scanned = 0
        td_ok = 0
        td_degraded = 0
        td_skipped = 0
        td_scan_ms_total = 0.0
        if td_cfg.enabled:
            # Supported chains for tick scanning (must have subgraph ID configured)
            supported_chains = set(td_cfg.uniswap_subgraph_ids.keys()) | set(td_cfg.uniswap_subgraph_endpoints.keys())

            # Build per-chain providers (reuse across candidates on same chain)
            chain_providers: dict[str, UniswapV3TickProvider] = {}
            for chain_name in supported_chains:
                endpoint = td_cfg.uniswap_subgraph_endpoints.get(chain_name)
                subgraph_id = td_cfg.uniswap_subgraph_ids.get(chain_name)
                if not endpoint and not subgraph_id:
                    continue
                try:
                    chain_providers[chain_name] = UniswapV3TickProvider(
                        endpoint=endpoint,
                        subgraph_id=subgraph_id,
                        graph_api_key_env=td_cfg.graph_api_key_env,
                        timeout_seconds=td_cfg.scan_timeout_seconds,
                        retry_attempts=td_cfg.retry_attempts,
                        max_pages_per_pool=td_cfg.max_pages_per_pool,
                        max_ticks_per_pool=td_cfg.max_ticks_per_pool,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Tick density provider init failed for %s: %s", chain_name, exc)

            # Resolve per-chain RPC URLs for slot0 cross-check
            chain_rpc_urls: dict[str, str] = {}
            for chain_name, env_var in td_cfg.rpc_url_env_map.items():
                rpc_url = os.getenv(env_var, "").strip()
                if rpc_url:
                    chain_rpc_urls[chain_name] = rpc_url

            # CLMM project keywords for candidate selection
            clmm_projects = {"uniswap", "uniswap-v3", "sushiswap", "pancakeswap", "aerodrome", "camelot"}

            # Select candidates for scanning
            scan_candidates = []
            for opt in opportunities:
                c = opt.candidate
                project_lower = (c.project or "").lower().replace(" ", "")
                chain = c.chain or ""
                if chain not in supported_chains:
                    td_skipped += 1
                    continue
                if not any(kw in project_lower for kw in clmm_projects):
                    td_skipped += 1
                    continue
                if not c.address:
                    td_skipped += 1
                    continue
                scan_candidates.append(opt)

            # Limit to max_scan_candidates (sorted by TVL desc for priority)
            scan_candidates.sort(key=lambda o: float(o.candidate.tvl_usd or 0), reverse=True)
            scan_candidates = scan_candidates[:td_cfg.max_scan_candidates]

            for opt in scan_candidates:
                c = opt.candidate
                chain = c.chain or ""
                provider = chain_providers.get(chain)
                if provider is None:
                    td_skipped += 1
                    continue

                pool_addr = (c.address or "").strip().lower()
                if not pool_addr.startswith("0x"):
                    td_skipped += 1
                    continue

                # RPC slot0 cross-check (optional, fail-safe)
                rpc_tick = None
                rpc_url = chain_rpc_urls.get(chain)
                if rpc_url:
                    try:
                        rpc_tick = await fetch_slot0_tick(
                            rpc_url, pool_addr, timeout_seconds=td_cfg.rpc_timeout_seconds,
                        )
                    except Exception:  # noqa: BLE001
                        pass  # slot0 failure is non-fatal

                scan_start = time()
                try:
                    band_result = await scan_pool_band_depth(
                        provider, pool_addr,
                        rpc_tick=rpc_tick,
                        enforce_rpc_check=rpc_tick is not None,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Tick scan error pool=%s: %s", pool_addr[:10], exc.__class__.__name__)
                    td_degraded += 1
                    opt.metadata["tick_data_quality"] = "ERROR"
                    continue
                scan_elapsed_ms = (time() - scan_start) * 1000.0
                td_scan_ms_total += scan_elapsed_ms
                td_scanned += 1

                # Attach band depth fields to metadata
                opt.metadata["tick_data_quality"] = band_result.data_quality.value
                opt.metadata["band_depth_1pct_usd"] = f"{band_result.band_depth_1pct_usd:.2f}"
                opt.metadata["band_depth_2_5pct_usd"] = f"{band_result.band_depth_2_5pct_usd:.2f}"
                opt.metadata["band_depth_5pct_usd"] = f"{band_result.band_depth_5pct_usd:.2f}"
                opt.metadata["tick_pit_type"] = band_result.pit_type.value
                opt.metadata["tick_pits_found"] = str(band_result.pits_found)
                if band_result.degradation_reason:
                    opt.metadata["tick_degradation_reason"] = band_result.degradation_reason.value

                if band_result.data_quality == DataQuality.OK:
                    td_ok += 1
                else:
                    td_degraded += 1

            logger.info(
                "Tick density scan: scanned=%s ok=%s degraded=%s skipped=%s scan_ms_total=%.0f enabled=%s shadow=%s",
                td_scanned, td_ok, td_degraded, td_skipped, td_scan_ms_total,
                td_cfg.enabled, td_cfg.shadow_mode_enabled,
            )
        else:
            logger.info("Tick density scan disabled.")

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
            # Tick density: downgrade to WATCHLIST if data quality is degraded
            if td_cfg.enabled and not td_cfg.shadow_mode_enabled:
                tick_quality = opt.metadata.get("tick_data_quality", "")
                if tick_quality and tick_quality not in {"OK", ""}:
                    opt.metadata["report_group"] = "WATCHLIST"
                    opt.metadata.setdefault("watchlist_reason", tick_quality)
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
        apply_confidence_factors(report_picks, config.confidence_factors)

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
        if getattr(config.reporting, "telegram_shadow_mode_enabled", False):
            shadow_summary = shadow_tracker.process(report_picks)
            logger.info(shadow_summary.to_log_line())
        if getattr(config.reporting, "telegram_recheck_enabled", False):
            recheck_cache = CacheController(namespace="telegram_recheck")
            offset_raw = recheck_cache.get("offset")
            try:
                offset = int(offset_raw) if offset_raw is not None else None
            except (TypeError, ValueError):
                offset = None
            poll_limit = int(getattr(config.reporting, "telegram_recheck_poll_limit", 20) or 20)
            command = str(getattr(config.reporting, "telegram_recheck_command", "/recheck") or "/recheck")
            requests, next_offset = await notifier.fetch_recheck_requests(
                offset=offset,
                limit=poll_limit,
                command=command,
            )
            if next_offset is not None and next_offset != offset:
                recheck_cache.set("offset", int(next_offset), ttl_seconds=365 * 24 * 3600)

            # Bootstrap: first poll only advances offset and avoids replaying stale commands.
            if offset is None and requests:
                logger.info(
                    "Recheck command poll bootstrapped: skipped=%s (offset initialized=%s).",
                    len(requests),
                    next_offset,
                )
                requests = []

            threshold_pct = float(getattr(config.reporting, "telegram_recheck_change_threshold_pct", 20.0) or 20.0)
            handled = 0
            for pool_id in requests[:5]:
                handled += 1
                candidate = await client.get_pool_by_id(pool_id)
                if candidate is None:
                    await notifier.send_markdown_report(
                        "\n".join(
                            [
                                "*LP Re-check*",
                                f"❌ Pool not found: `{pool_id}`",
                                "Reason: pool id is absent in current DeFiLlama snapshot.",
                            ]
                        )
                    )
                    continue

                current_net_1k = (1000.0 * (float(candidate.apy or 0.0) / 100.0) / 12.0) - config.gas_efficiency.monthly_gas_cost_usd
                baseline = shadow_tracker.latest_prediction(pool_id)
                baseline_value = None
                if isinstance(baseline, dict):
                    baseline_value = baseline.get("predicted_net_profit_1k")
                try:
                    baseline_net_1k = float(baseline_value) if baseline_value is not None else None
                except (TypeError, ValueError):
                    baseline_net_1k = None

                decision_line = "⚪ NEED_BASELINE — no prior shadow snapshot for this pool."
                delta_line = "Δproxy: n/a"
                if baseline_net_1k is not None and abs(baseline_net_1k) > 1e-9:
                    delta_pct = abs(current_net_1k - baseline_net_1k) / abs(baseline_net_1k) * 100.0
                    delta_line = f"Δproxy: {delta_pct:.1f}% (threshold {threshold_pct:.1f}%)"
                    if delta_pct <= threshold_pct:
                        decision_line = "✅ CONFIRMED — proxy change within threshold."
                    else:
                        decision_line = "❌ ABORT — proxy change exceeds threshold."

                await notifier.send_markdown_report(
                    "\n".join(
                        [
                            "*LP Re-check*",
                            f"Pool: `{candidate.chain}` `{candidate.symbol}` | `{candidate.project}`",
                            f"Pool ID: `{pool_id}`",
                            f"Current APY: {float(candidate.apy or 0.0):.2f}% | TVL: {float(candidate.tvl_usd or 0.0):,.0f} USD",
                            f"Current proxy Net@1k: {current_net_1k:.2f}/mo",
                            f"Baseline proxy Net@1k: {baseline_net_1k:.2f}/mo" if baseline_net_1k is not None else "Baseline proxy Net@1k: n/a",
                            delta_line,
                            decision_line,
                            f"[Pool](https://defillama.com/yields/pool/{pool_id})",
                            "_Note: re-check uses shadow proxy (net@1k delta), not on-chain band-depth yet._",
                        ]
                    )
                )
            if handled > 0:
                logger.info("Processed recheck commands: count=%s.", handled)
        logger.info(
            "Freshness summary: rechecked=%s fresh=%s stale=%s unverified=%s diverged=%s downgraded=%s "
            "aave_checked=%s aave_ok=%s aave_timeout=%s aave_error=%s aave_schema_mismatch=%s aave_addr_mismatch=%s "
            "morpho_checked=%s morpho_ok=%s morpho_timeout=%s morpho_error=%s morpho_schema_mismatch=%s morpho_addr_mismatch=%s "
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
            freshness_counts["morpho_checked_count"],
            freshness_counts["morpho_ok_count"],
            freshness_counts["morpho_timeout_count"],
            freshness_counts["morpho_error_count"],
            freshness_counts["morpho_schema_mismatch_count"],
            freshness_counts["morpho_addr_mismatch_count"],
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
                    my_pools_report=my_pools_report,
                )
                _mark_telegram_digest_sent()
                logger.info(
                    "Reported %s opportunities (safe=%s warn=%s actionable=%s watchlist=%s shadow=%s).",
                    len(report_picks),
                    len(safe_picks),
                    len(warn_picks),
                    actionable_count,
                    watchlist_count,
                    bool(getattr(config.reporting, "telegram_shadow_mode_enabled", False)),
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
            due, interval, remaining = _telegram_no_opps_heartbeat_due(config)
            if due:
                heartbeat_lines = [
                    "*Scout Heartbeat*",
                    "No opportunities found in current cycle.",
                    f"- Eligible after L3: {len(eligible)}",
                    f"- Safe picks: {len(safe_picks)} | Warn picks: {len(warn_picks)}",
                    f"- Freshness recheck enabled: {config.freshness.recheck_enabled}",
                ]
                if config.my_pools_monitor.enabled and my_pools_report is not None:
                    heartbeat_lines.append(
                        f"- My Pools: configured={len(config.my_pools_monitor.pools)} "
                        f"snapshots={len(getattr(my_pools_report, 'snapshots', []) or [])} "
                        f"watch={int(getattr(my_pools_report, 'watch_count', 0) or 0)}"
                    )
                await notifier.send_markdown_report("\n".join(heartbeat_lines))
                _mark_telegram_no_opps_heartbeat_sent()
                logger.info("No-op heartbeat sent (interval=%ss).", interval)
            else:
                logger.info(
                    "Match not found. No-op heartbeat suppressed by schedule: interval=%ss next_in=%ss.",
                    interval,
                    remaining,
                )

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
