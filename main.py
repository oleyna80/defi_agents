import asyncio
import logging
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from time import time

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from defi_agents.scout.config import ExecutionChainConfig, ScoutConfig
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
from defi_agents.freshness import (
    FreshnessManager,
    apply_confidence_factors,
    apply_freshness_policy,
)
from defi_agents.history import save_to_history
from defi_agents.shadow_metrics import ShadowMetricsTracker
from defi_agents.strategy_sim.engine import StrategySimEngine
from defi_agents.strategy_sim.models import SimulationCounters
from defi_agents.lp.band_depth import scan_pool_band_depth
from defi_agents.lp.entry_recommendation import (
    build_ineligible_entry_recommendations,
    build_entry_recommendations,
    filter_lp_entry_target_scope,
    is_lp_entry_target_scope_match,
    normalize_pair_for_target_matching,
    split_lp_entry_eligibility,
    summarize_watchlist_blocker_reason_counts,
    summarize_watchlist_reason_counts,
)
from defi_agents.lp.readiness import (
    READINESS_BLOCKER_GRAPH_API_KEY_MISSING,
    READINESS_BLOCKER_RPC_TICK_UNAVAILABLE,
    READINESS_BLOCKER_SUBGRAPH_SCHEMA_UNSUPPORTED,
    READINESS_BLOCKER_TICK_PROVIDER_INIT_ERROR,
    READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR,
    normalize_readiness_blocker_code,
    readiness_blocker_from_tick_degradation_reason,
)
from defi_agents.lp.stability import (
    compute_stability_observation_counts,
    normalize_pool_ids,
    summarize_entry_stability_telemetry,
)
from defi_agents.lp.tick_provider import TickProviderError, UniswapV3TickProvider
from defi_agents.lp.rpc_helper import fetch_slot0_tick
from defi_agents.lp.models import DataQuality
from defi_agents.lp.volatility import estimate_vol
from defi_agents.lp.runtime_metrics import summarize_tick_scan_runtime_metrics
from defi_agents.tracker.position_reader import BaseUniswapV3PositionReader
from defi_agents.execution import (
    ExecutionOrchestrator,
    FailoverExecutionAdapter,
    KrystalExecutionAdapter,
    NativeLiveExecutionAdapter,
    NativeUniswapV3Adapter,
    PolicyGuard,
    PositionState,
    TriggerEngine,
    V3UtilsExecutionAdapter,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Sentinel")
# Prevent accidental secret leaks in verbose HTTP request logs (e.g., Telegram bot token in URL path).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _format_reason_counts_for_log(counts: Mapping[str, int] | None) -> str:
    if not counts:
        return "NONE"
    parts: list[str] = []
    for key in sorted(str(k).strip().upper() for k in counts.keys() if str(k).strip()):
        value = int(counts.get(key, 0) or 0)
        if value < 0:
            continue
        parts.append(f"{key}:{value}")
    return ",".join(parts) if parts else "NONE"


def _select_primary_readiness_blocker(counts: Mapping[str, int] | None) -> str | None:
    if not counts:
        return None
    ranked: list[tuple[str, int]] = []
    for raw_code, raw_count in counts.items():
        code = normalize_readiness_blocker_code(raw_code)
        if not code:
            continue
        try:
            count = int(str(raw_count).strip())
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        ranked.append((code, count))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked[0][0]


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


def _to_float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_tick_range_from_metadata(
    metadata: Mapping[str, str],
) -> tuple[int | None, int | None]:
    lower_raw = metadata.get("suggested_range_lower_tick")
    upper_raw = metadata.get("suggested_range_upper_tick")
    try:
        lower_tick = int(lower_raw) if lower_raw not in (None, "") else None
        upper_tick = int(upper_raw) if upper_raw not in (None, "") else None
    except (TypeError, ValueError):
        return None, None
    return lower_tick, upper_tick


def _range_watchlist_reason(
    lower_tick: int | None, upper_tick: int | None
) -> str | None:
    if lower_tick is None and upper_tick is None:
        return "RANGE_NOT_COMPUTED"
    if lower_tick is None or upper_tick is None or lower_tick >= upper_tick:
        return "INVALID_OR_MISSING_RANGE"
    return None


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = int(round((len(ordered) - 1) * max(0.0, min(1.0, q))))
    return ordered[pos]


def _freshness_divergence_stats(
    results,
) -> dict[
    str, tuple[int, float | None, float | None, float | None, float | None]
]:  # noqa: ANN001
    stats: dict[str, dict[str, list[float]]] = {}
    for r in results:
        provider = (
            str((r.metadata or {}).get("freshness_provider", "") or "").strip()
            or "none"
        )
        apy_div = _to_float_or_none((r.metadata or {}).get("apy_divergence_pct"))
        tvl_div = _to_float_or_none((r.metadata or {}).get("tvl_divergence_pct"))
        if provider not in stats:
            stats[provider] = {"apy": [], "tvl": []}
        if apy_div is not None:
            stats[provider]["apy"].append(apy_div)
        if tvl_div is not None:
            stats[provider]["tvl"].append(tvl_div)

    out: dict[
        str, tuple[int, float | None, float | None, float | None, float | None]
    ] = {}
    for provider, values in stats.items():
        apy_vals = values["apy"]
        tvl_vals = values["tvl"]
        sample_size = max(len(apy_vals), len(tvl_vals))
        out[provider] = (
            sample_size,
            _percentile(apy_vals, 0.5),
            _percentile(apy_vals, 0.9),
            _percentile(tvl_vals, 0.5),
            _percentile(tvl_vals, 0.9),
        )
    return out


def _telegram_digest_due(config: ScoutConfig) -> tuple[bool, int, int]:
    interval = int(
        getattr(
            getattr(config, "reporting", None), "telegram_digest_interval_seconds", 0
        )
        or 0
    )
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
    enabled = bool(
        getattr(reporting, "telegram_no_opportunities_heartbeat_enabled", False)
    )
    interval = int(
        getattr(reporting, "telegram_no_opportunities_heartbeat_interval_seconds", 0)
        or 0
    )
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


async def _load_execution_states(config: ScoutConfig) -> list[PositionState]:
    wallet_address = os.getenv("WALLET_ADDRESS", "").strip()

    if not wallet_address:
        logger.warning(
            "Execution state source unavailable: reason=WALLET_ADDRESS_MISSING source=position_reader"
        )
        return []

    chains = dict(config.execution.chains)
    if not chains:
        logger.warning(
            "Execution state source unavailable: reason=EXECUTION_CHAINS_EMPTY source=position_reader"
        )
        return []

    states: list[PositionState] = []
    failed_chains: list[str] = []
    stale_count = 0
    for chain_name in sorted(chains.keys(), key=lambda item: str(item).lower()):
        chain_cfg = chains[chain_name]
        try:
            reader = _build_execution_position_reader(
                chain_name=chain_name,
                chain_cfg=chain_cfg,
            )
            chain_states = await reader.load_active_position_states(wallet_address)
        except Exception as exc:  # noqa: BLE001
            err_class = getattr(exc, "reason_code", exc.__class__.__name__)
            logger.warning(
                "Execution state source degraded: chain=%s reason=POSITION_READER_ERROR err=%s source=position_reader",
                chain_name,
                err_class,
            )
            failed_chains.append(str(chain_name))
            continue

        chain_stale_count = sum(1 for state in chain_states if state.stale)
        stale_count += chain_stale_count
        logger.info(
            "Execution states loaded: source=position_reader chain=%s active_states=%s",
            chain_name,
            len(chain_states),
        )
        states.extend(chain_states)

    if len(failed_chains) == len(chains):
        failed_chains_csv = ",".join(sorted(failed_chains, key=lambda item: item.lower()))
        logger.error(
            "Execution state source failed: reason=POSITION_READER_ALL_CHAINS_FAILED failed_chains=%s source=position_reader",
            failed_chains_csv,
        )
        raise RuntimeError("POSITION_READER_ALL_CHAINS_FAILED")

    if not states:
        logger.warning(
            "Execution state source empty: reason=NO_ACTIVE_POSITIONS source=position_reader"
        )
        return []

    states = sorted(states, key=_execution_state_sort_key)

    if stale_count > 0:
        logger.warning(
            "Execution state quality: source=position_reader stale_states=%s reason=STALE_POSITION_DATA mode=%s",
            stale_count,
            config.execution.mode,
        )

    return states


def _build_execution_position_reader(
    *,
    chain_name: str,
    chain_cfg: ExecutionChainConfig,
) -> BaseUniswapV3PositionReader:
    return BaseUniswapV3PositionReader(
        chain_name=chain_name,
        rpc_url=chain_cfg.rpc_url,
        coingecko_platform_id=chain_cfg.coingecko_platform_id,
        position_manager_address=chain_cfg.uniswap_v3.position_manager_proxy,
        factory_address=chain_cfg.uniswap_v3.factory_proxy,
    )


def _execution_state_sort_key(state: PositionState) -> tuple[str, int, str]:
    chain_name = str(state.chain or "").strip().lower()
    token_id = _position_state_token_id(state)
    return (chain_name, token_id, str(state.position_ref or ""))


def _position_state_token_id(state: PositionState) -> int:
    metadata = state.metadata if isinstance(state.metadata, dict) else {}
    token_id_raw = metadata.get("token_id")
    try:
        return int(token_id_raw)
    except (TypeError, ValueError):
        pass
    match = re.search(r"uni-v3:(\d+)$", str(state.position_ref or ""))
    if match is None:
        return sys.maxsize
    return int(match.group(1))


def _build_execution_adapter(config: ScoutConfig):
    exec_cfg = config.execution
    strict_live = exec_cfg.mode == "LIVE"

    def _supports_live_execution(adapter: object) -> bool:
        return bool(getattr(adapter, "supports_live_execution", False))

    def _build_one(name: str):
        if name == "krystal":
            api_key = os.getenv(exec_cfg.krystal_api_key_env, "").strip()
            if not api_key:
                raise RuntimeError("KRYSTAL_API_KEY_MISSING")
            return KrystalExecutionAdapter(
                base_url=exec_cfg.krystal_base_url,
                api_key=api_key,
                timeout_seconds=exec_cfg.krystal_timeout_seconds,
            )
        if name in ("native_uniswap_v3_live", "uniswap_v3_live"):
            rpc_urls: dict[str, str] = {}
            for chain, env_name in dict(exec_cfg.native_live_rpc_env_by_chain).items():
                rpc_url = os.getenv(str(env_name), "").strip()
                if rpc_url:
                    rpc_urls[str(chain)] = rpc_url
            return NativeLiveExecutionAdapter(
                rpc_urls=rpc_urls,
                timeout_seconds=exec_cfg.native_live_timeout_seconds,
                receipt_timeout_seconds=exec_cfg.native_live_receipt_timeout_seconds,
                receipt_poll_seconds=exec_cfg.native_live_receipt_poll_seconds,
            )
        if name in ("v3utils", "v3utils_live"):
            if not exec_cfg.v3utils_enabled:
                raise RuntimeError("V3UTILS_DISABLED")
            rpc_urls: dict[str, str] = {}
            for chain, env_name in dict(exec_cfg.native_live_rpc_env_by_chain).items():
                rpc_url = os.getenv(str(env_name), "").strip()
                if rpc_url:
                    rpc_urls[str(chain)] = rpc_url
            return V3UtilsExecutionAdapter(
                rpc_urls=rpc_urls,
                contracts_by_chain=exec_cfg.v3utils_contracts_by_chain,
                routers_by_chain=exec_cfg.v3utils_router_by_chain,
                default_slippage_bps=exec_cfg.v3utils_slippage_bps_default,
                timeout_seconds=exec_cfg.native_live_timeout_seconds,
                receipt_timeout_seconds=exec_cfg.native_live_receipt_timeout_seconds,
                receipt_poll_seconds=exec_cfg.native_live_receipt_poll_seconds,
            )
        # "native_uniswap_v3" | "uniswap_v3_simulate" → simulate adapter (PAPER/SHADOW baseline)
        return NativeUniswapV3Adapter()

    if strict_live:
        candidate_names: list[str] = [exec_cfg.primary_adapter]
        if exec_cfg.fallback_adapter != exec_cfg.primary_adapter:
            candidate_names.append(exec_cfg.fallback_adapter)

        errors: list[str] = []
        for name in candidate_names:
            try:
                adapter = _build_one(name)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Execution LIVE adapter init failed: adapter=%s err=%s",
                    name,
                    exc.__class__.__name__,
                )
                errors.append(f"{name}:{exc.__class__.__name__}")
                continue

            if not _supports_live_execution(adapter):
                logger.error(
                    "Execution LIVE adapter rejected: adapter=%s reason=NOT_LIVE_CAPABLE",
                    name,
                )
                errors.append(f"{name}:NOT_LIVE_CAPABLE")
                continue

            logger.info("Execution LIVE adapter selected: adapter=%s", name)
            return adapter

        raise RuntimeError(f"LIVE_EXECUTION_ADAPTER_UNAVAILABLE ({','.join(errors)})")

    primary = None
    try:
        primary = _build_one(exec_cfg.primary_adapter)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Execution primary adapter init failed: adapter=%s err=%s",
            exec_cfg.primary_adapter,
            exc.__class__.__name__,
        )

    if primary is None:
        try:
            primary = _build_one(exec_cfg.fallback_adapter)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Execution fallback adapter init failed: adapter=%s err=%s",
                exec_cfg.fallback_adapter,
                exc.__class__.__name__,
            )

    if primary is None:
        logger.warning(
            "Execution adapter init failed for configured adapters; using native fallback."
        )
        return NativeUniswapV3Adapter()

    if exec_cfg.fallback_adapter == exec_cfg.primary_adapter:
        return primary

    try:
        fallback = _build_one(exec_cfg.fallback_adapter)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Execution secondary fallback init failed: adapter=%s err=%s; using native fallback",
            exec_cfg.fallback_adapter,
            exc.__class__.__name__,
        )
        fallback = NativeUniswapV3Adapter()

    if primary.__class__ is fallback.__class__:
        return primary
    return FailoverExecutionAdapter(primary, fallback, logger_name="Sentinel")


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
            logger.warning(
                "AI init failed: %s. Falling back to MockAI (dev mode).", exc
            )
            provider = MockAIService()
        else:
            logger.critical("AI init failed and fallback disabled. Stopping startup.")
            raise RuntimeError("Production AI Init Failure") from exc
    l3_manager = L3AnalysisManager(config=config, provider=provider)
    notifier = TelegramNotifier(
        include_tags=config.risk_policy.include_tags_in_report,
        top_n_per_section=getattr(config.reporting, "telegram_top_n_per_section", 0),
        show_opportunity_sections=getattr(
            config.reporting, "telegram_opportunity_sections_enabled", True
        ),
        show_source_confidence=getattr(
            config.reporting, "telegram_show_source_confidence", True
        ),
        show_market_signals=getattr(
            config.reporting, "telegram_show_market_signals", False
        ),
        chat_id_env=(
            getattr(
                config.reporting,
                "telegram_shadow_chat_id_env",
                "TELEGRAM_SHADOW_CHAT_ID",
            )
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
            getattr(
                config.reporting,
                "telegram_shadow_chat_id_env",
                "TELEGRAM_SHADOW_CHAT_ID",
            ),
            int(getattr(config.reporting, "telegram_digest_interval_seconds", 0) or 0),
        )
    shadow_tracker = ShadowMetricsTracker(
        horizon_seconds=int(
            getattr(config.reporting, "telegram_shadow_metrics_horizon_seconds", 86_400)
            or 86_400
        ),
        capture_interval_seconds=int(
            getattr(
                config.reporting, "telegram_shadow_capture_interval_seconds", 21_600
            )
            or 21_600
        ),
        retention_seconds=int(
            getattr(config.reporting, "telegram_shadow_retention_seconds", 1_209_600)
            or 1_209_600
        ),
    )

    logger.info("Starting Global Scout Cycle (chains: ALL).")

    try:
        if getattr(config.reporting, "telegram_directional_sections_enabled", False):
            try:
                directional_snapshot = await client.get_directional_snapshot()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Directional snapshot fetch failed: %s", exc.__class__.__name__
                )
                directional_snapshot = None
        if getattr(config.reporting, "telegram_turnover_section_enabled", False):
            try:
                turnover_snapshot = await client.get_turnover_snapshot()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Turnover snapshot fetch failed: %s", exc.__class__.__name__
                )
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
        td_discovery_scanned = 0
        td_discovery_ok = 0
        td_discovery_degraded = 0
        td_discovery_skipped = 0
        td_scan_ms_total = 0.0
        td_scan_durations_ms: list[float] = []
        td_scan_results = []
        td_readiness_blockers: dict[str, int] = {}
        if td_cfg.enabled:
            def _inc_td_blocker(code: str) -> None:
                normalized = normalize_readiness_blocker_code(code)
                if not normalized:
                    return
                td_readiness_blockers[normalized] = (
                    int(td_readiness_blockers.get(normalized, 0)) + 1
                )

            def _provider_init_blocker_code_from_exception(exc: Exception) -> str:
                message = str(exc or "")
                if "Missing env `GRAPH_API_KEY`" in message:
                    return READINESS_BLOCKER_GRAPH_API_KEY_MISSING
                if isinstance(exc, ValueError) and td_cfg.graph_api_key_env in message:
                    return READINESS_BLOCKER_GRAPH_API_KEY_MISSING
                return READINESS_BLOCKER_TICK_PROVIDER_INIT_ERROR

            async def _build_chain_providers(
                *,
                venue: str,
                subgraph_endpoints: dict[str, str],
                subgraph_ids: dict[str, str],
            ) -> dict[str, UniswapV3TickProvider]:
                providers: dict[str, UniswapV3TickProvider] = {}
                chains = set(subgraph_ids.keys()) | set(subgraph_endpoints.keys())
                for chain_name in chains:
                    endpoint = subgraph_endpoints.get(chain_name)
                    subgraph_id = subgraph_ids.get(chain_name)
                    if not endpoint and not subgraph_id:
                        continue
                    try:
                        provider = UniswapV3TickProvider(
                            endpoint=endpoint,
                            subgraph_id=subgraph_id,
                            graph_api_key_env=td_cfg.graph_api_key_env,
                            timeout_seconds=td_cfg.scan_timeout_seconds,
                            retry_attempts=td_cfg.retry_attempts,
                            max_pages_per_pool=td_cfg.max_pages_per_pool,
                            max_ticks_per_pool=td_cfg.max_ticks_per_pool,
                        )
                        try:
                            supports = await provider.supports_tick_schema()
                        except TickProviderError as exc:
                            # Fail-safe: treat as "disabled this cycle" (likely downtime/rate-limit),
                            # not as a hard init failure.
                            _inc_td_blocker(READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR)
                            logger.warning(
                                "Tick density provider unavailable: venue=%s chain=%s reason=%s msg=%s",
                                venue,
                                chain_name,
                                getattr(exc.reason, "value", str(exc.reason)),
                                str(exc)[:220],
                            )
                            continue
                        if not supports:
                            # Unsupported schema is expected on some subgraphs and is handled fail-safe.
                            # Keep this as INFO to avoid alert fatigue in routine shadow runs.
                            _inc_td_blocker(
                                READINESS_BLOCKER_SUBGRAPH_SCHEMA_UNSUPPORTED
                            )
                            logger.info(
                                "Tick density provider disabled (schema unsupported): venue=%s chain=%s",
                                venue,
                                chain_name,
                            )
                            continue
                        providers[chain_name] = provider
                    except TickProviderError as exc:
                        _inc_td_blocker(READINESS_BLOCKER_TICK_PROVIDER_INIT_ERROR)
                        logger.warning(
                            "Tick density provider init failed: venue=%s chain=%s reason=%s msg=%s",
                            venue,
                            chain_name,
                            getattr(exc.reason, "value", str(exc.reason)),
                            str(exc)[:220],
                        )
                    except Exception as exc:  # noqa: BLE001
                        _inc_td_blocker(_provider_init_blocker_code_from_exception(exc))
                        logger.warning(
                            "Tick density provider init failed: venue=%s chain=%s err=%s msg=%s",
                            venue,
                            chain_name,
                            exc.__class__.__name__,
                            str(exc)[:220],
                        )
                return providers

            uniswap_chain_providers = await _build_chain_providers(
                venue="uniswap",
                subgraph_endpoints=td_cfg.uniswap_subgraph_endpoints,
                subgraph_ids=td_cfg.uniswap_subgraph_ids,
            )
            aerodrome_chain_providers = await _build_chain_providers(
                venue="aerodrome",
                subgraph_endpoints=td_cfg.aerodrome_subgraph_endpoints,
                subgraph_ids=td_cfg.aerodrome_subgraph_ids,
            )

            # Resolve per-chain RPC URLs for slot0 cross-check
            chain_rpc_urls: dict[str, str] = {}
            for chain_name, env_var in td_cfg.rpc_url_env_map.items():
                rpc_url = os.getenv(env_var, "").strip()
                if rpc_url:
                    chain_rpc_urls[chain_name] = rpc_url

            def _provider_for_candidate(
                candidate,
            ) -> UniswapV3TickProvider | None:  # noqa: ANN001
                project_lower = (candidate.project or "").lower().replace(" ", "")
                chain = candidate.chain or ""
                if "aerodrome-slipstream" in project_lower:
                    return aerodrome_chain_providers.get(chain)
                if "uniswap-v3" in project_lower or "uniswapv3" in project_lower:
                    return uniswap_chain_providers.get(chain)
                return None

            def _normalize_evm_address(value: object) -> str | None:
                if not isinstance(value, str):
                    return None
                raw = value.strip()
                if ":" in raw:
                    raw = raw.split(":")[-1].strip()
                if re.fullmatch(r"0x[a-fA-F0-9]{40}", raw):
                    return raw.lower()
                return None

            def _token_pair(candidate) -> tuple[str, str] | None:  # noqa: ANN001
                normalized_tokens: list[str] = []
                for raw_token in list(
                    getattr(candidate, "underlying_tokens", []) or []
                ):
                    normalized = _normalize_evm_address(raw_token)
                    if normalized and normalized not in normalized_tokens:
                        normalized_tokens.append(normalized)
                if len(normalized_tokens) < 2:
                    return None
                return normalized_tokens[0], normalized_tokens[1]

            def _parse_fee_tier(pool_meta: str | None) -> int | None:
                raw = str(pool_meta or "").strip()
                if not raw:
                    return None
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", raw)
                if not match:
                    return None
                try:
                    pct_value = float(match.group(1))
                except ValueError:
                    return None
                if pct_value <= 0:
                    return None
                return max(1, int(round(pct_value * 10_000.0)))

            def _candidate_scan_eligible(candidate) -> bool:  # noqa: ANN001
                direct = _normalize_evm_address(candidate.address)
                if direct and (candidate.address_source or "").upper() == "POOL":
                    return True
                return _token_pair(candidate) is not None

            pool_resolve_cache: dict[tuple[str, str, str, int | None], str | None] = {}
            scanned_pool_addrs: set[str] = set()

            async def _resolve_scan_pool_address(
                provider: UniswapV3TickProvider,
                candidate,
                metadata: dict[str, str] | None,
            ) -> str | None:  # noqa: ANN001
                direct = _normalize_evm_address(candidate.address)
                if direct and (candidate.address_source or "").upper() == "POOL":
                    return direct

                pair = _token_pair(candidate)
                if pair is None:
                    return None

                fee_tier = _parse_fee_tier(getattr(candidate, "pool_meta", None))
                token0, token1 = pair
                cache_key = (
                    provider.endpoint,
                    min(token0, token1),
                    max(token0, token1),
                    fee_tier,
                )
                if cache_key not in pool_resolve_cache:
                    resolved = await provider.find_pool_address_by_tokens(
                        token0,
                        token1,
                        fee_tier=fee_tier,
                    )
                    pool_resolve_cache[cache_key] = resolved
                resolved = pool_resolve_cache.get(cache_key)
                if resolved and metadata is not None:
                    metadata["tick_pool_address"] = resolved
                    metadata["tick_pool_source"] = "TOKEN_RESOLVER"
                    if fee_tier is not None:
                        metadata["tick_pool_fee_tier"] = str(fee_tier)
                return resolved

            # Select shortlist candidates for scanning
            scan_candidates: list[tuple[object, UniswapV3TickProvider]] = []
            for opt in opportunities:
                c = opt.candidate
                provider = _provider_for_candidate(c)
                if provider is None:
                    td_skipped += 1
                    continue
                if not _candidate_scan_eligible(c):
                    td_skipped += 1
                    continue
                scan_candidates.append((opt, provider))

            # Limit shortlist scan scope by TVL priority.
            scan_candidates.sort(
                key=lambda entry: float(entry[0].candidate.tvl_usd or 0), reverse=True
            )
            scan_candidates = scan_candidates[: td_cfg.max_scan_candidates]
            # Cache vol estimates per pool for this cycle to avoid duplicate historical lookups.
            vol_cache: dict[str, tuple[float, float, int, float] | None] = {}

            # Returns: ok | degraded | error | skip, plus resolved pool address if any.
            async def _scan_tick_candidate(
                provider: UniswapV3TickProvider,
                candidate,
                metadata: dict[str, str] | None,
            ) -> tuple[str, str | None]:  # noqa: ANN001
                nonlocal td_scanned, td_ok, td_degraded, td_scan_ms_total

                pool_addr = await _resolve_scan_pool_address(
                    provider, candidate, metadata
                )
                if not pool_addr:
                    return "skip", None
                if pool_addr in scanned_pool_addrs:
                    return "skip", pool_addr
                scanned_pool_addrs.add(pool_addr)

                # DeFiLlama price-based daily volatility (token0/token1 ratio) for scan-stage metadata.
                # This is fail-safe and optional: scan continues even when vol data is unavailable.
                vol_key = str(candidate.pool_id or pool_addr)
                if vol_key not in vol_cache:
                    vol_cache[vol_key] = None
                    try:
                        ratio_prices = await client.get_pair_price_ratio_history(
                            candidate, lookback_days=10
                        )
                        vol_est = estimate_vol(ratio_prices, holding_days=7.0)
                        if vol_est is not None:
                            vol_cache[vol_key] = (
                                float(vol_est.daily_vol),
                                float(vol_est.annual_vol),
                                int(vol_est.sample_days),
                                float(vol_est.range_half_width_pct),
                            )
                    except Exception:  # noqa: BLE001
                        pass
                vol_info = vol_cache.get(vol_key)
                daily_vol_for_scan: float | None = None
                if metadata is not None and vol_info is not None:
                    daily_vol, annual_vol, sample_days, range_half_width = vol_info
                    daily_vol_for_scan = float(daily_vol)
                    metadata["tick_daily_vol"] = f"{daily_vol:.6f}"
                    metadata["tick_annual_vol"] = f"{annual_vol:.6f}"
                    metadata["tick_vol_samples"] = str(sample_days)
                    metadata["tick_range_half_width_pct"] = (
                        f"{range_half_width * 100.0:.2f}"
                    )
                elif vol_info is not None:
                    daily_vol_for_scan = float(vol_info[0])

                # RPC slot0 cross-check (optional, fail-safe)
                rpc_tick = None
                rpc_url = chain_rpc_urls.get(candidate.chain or "")
                if rpc_url:
                    try:
                        rpc_tick = await fetch_slot0_tick(
                            rpc_url,
                            pool_addr,
                            timeout_seconds=td_cfg.rpc_timeout_seconds,
                        )
                    except Exception:  # noqa: BLE001
                        rpc_tick = None
                    if rpc_tick is None:
                        _inc_td_blocker(READINESS_BLOCKER_RPC_TICK_UNAVAILABLE)

                scan_start = time()
                try:
                    band_result = await scan_pool_band_depth(
                        provider,
                        pool_addr,
                        rpc_tick=rpc_tick,
                        enforce_rpc_check=rpc_tick is not None,
                        daily_vol=daily_vol_for_scan,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Tick scan error pool=%s: %s",
                        pool_addr[:10],
                        exc.__class__.__name__,
                    )
                    td_degraded += 1
                    if metadata is not None:
                        metadata["tick_data_quality"] = "ERROR"
                        metadata["readiness_blocker"] = (
                            READINESS_BLOCKER_TICK_PROVIDER_RUNTIME_ERROR
                        )
                    return "error", pool_addr

                scan_elapsed_ms = (time() - scan_start) * 1000.0
                td_scan_ms_total += scan_elapsed_ms
                td_scan_durations_ms.append(scan_elapsed_ms)
                td_scanned += 1
                td_scan_results.append(band_result)

                if metadata is not None:
                    metadata["tick_data_quality"] = band_result.data_quality.value
                    metadata["band_depth_1pct_usd"] = (
                        f"{band_result.band_depth_1pct_usd:.2f}"
                    )
                    metadata["band_depth_2_5pct_usd"] = (
                        f"{band_result.band_depth_2_5pct_usd:.2f}"
                    )
                    metadata["band_depth_5pct_usd"] = (
                        f"{band_result.band_depth_5pct_usd:.2f}"
                    )
                    metadata["pit_type"] = band_result.pit_type.value
                    metadata["pits_found"] = str(band_result.pits_found)
                    metadata["tick_pit_type"] = band_result.pit_type.value
                    metadata["tick_pits_found"] = str(band_result.pits_found)
                    if band_result.suggested_range_lower_tick is not None:
                        metadata["suggested_range_lower_tick"] = str(
                            band_result.suggested_range_lower_tick
                        )
                    if band_result.suggested_range_upper_tick is not None:
                        metadata["suggested_range_upper_tick"] = str(
                            band_result.suggested_range_upper_tick
                        )
                    if band_result.degradation_reason:
                        metadata["tick_degradation_reason"] = (
                            band_result.degradation_reason.value
                        )
                        blocker_reason = readiness_blocker_from_tick_degradation_reason(
                            band_result.degradation_reason.value
                        )
                        if blocker_reason:
                            metadata["readiness_blocker"] = blocker_reason

                if band_result.data_quality == DataQuality.OK:
                    td_ok += 1
                    return "ok", pool_addr

                td_degraded += 1
                return "degraded", pool_addr

            for opt, provider in scan_candidates:
                status, _pool_addr = await _scan_tick_candidate(
                    provider, opt.candidate, opt.metadata
                )
                if status == "skip":
                    td_skipped += 1

            # Secondary stream: scan discovered Uniswap pools even if they are not in shortlist.
            discovery_candidates_raw = list(
                getattr(scout, "last_discovery_candidates", []) or []
            )
            discovery_candidates: list[tuple[object, UniswapV3TickProvider]] = []
            discovery_seen_addrs: set[str] = set()
            for c in discovery_candidates_raw:
                provider = _provider_for_candidate(c)
                if provider is None:
                    td_discovery_skipped += 1
                    continue
                if not _candidate_scan_eligible(c):
                    td_discovery_skipped += 1
                    continue
                pool_addr_direct = _normalize_evm_address(c.address)
                if pool_addr_direct and (c.address_source or "").upper() == "POOL":
                    if (
                        pool_addr_direct in scanned_pool_addrs
                        or pool_addr_direct in discovery_seen_addrs
                    ):
                        continue
                    discovery_seen_addrs.add(pool_addr_direct)
                discovery_candidates.append((c, provider))

            discovery_candidates.sort(
                key=lambda entry: float(entry[0].tvl_usd or 0), reverse=True
            )
            discovery_candidates = discovery_candidates[: td_cfg.max_scan_candidates]
            for c, provider in discovery_candidates:
                status, _pool_addr = await _scan_tick_candidate(provider, c, None)
                if status == "ok":
                    td_discovery_scanned += 1
                    td_discovery_ok += 1
                elif status == "degraded":
                    td_discovery_scanned += 1
                    td_discovery_degraded += 1
                elif status == "error":
                    td_discovery_degraded += 1
                else:
                    td_discovery_skipped += 1

            td_skipped += td_discovery_skipped

            td_runtime_metrics = summarize_tick_scan_runtime_metrics(
                scan_results=td_scan_results,
                scan_durations_ms=td_scan_durations_ms,
            )
            logger.info(
                "Tick density scan: scanned=%s ok=%s degraded_count=%s skipped=%s "
                "discovery_scanned=%s discovery_ok=%s discovery_degraded=%s discovery_skipped=%s "
                "pits_found_count=%s confident_pit_count=%s scan_ms_total=%.0f scan_duration_p95_ms=%.0f "
                "enabled=%s shadow=%s",
                td_scanned,
                td_ok,
                td_degraded,
                td_skipped,
                td_discovery_scanned,
                td_discovery_ok,
                td_discovery_degraded,
                td_discovery_skipped,
                td_runtime_metrics.pits_found_count,
                td_runtime_metrics.confident_pit_count,
                td_scan_ms_total,
                td_runtime_metrics.scan_duration_p95_ms,
                td_cfg.enabled,
                td_cfg.shadow_mode_enabled,
            )
            logger.info(
                "Tick density readiness telemetry: blocker_counts=%s",
                _format_reason_counts_for_log(td_readiness_blockers),
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
            opt
            for opt in eligible
            if (
                _sec_status_value(opt) in {"trusted", "pass"}
                and opt.score >= safe_min_score
            )
        ]
        warn_picks = [
            opt
            for opt in eligible
            if (_sec_status_value(opt) == "warn" and opt.score >= warn_min_score)
        ]
        for opt in safe_picks:
            opt.metadata["bucket"] = "SAFE"
        for opt in warn_picks:
            reasons = {
                r.strip()
                for r in opt.metadata.get("warn_reasons", "").split(",")
                if r.strip()
            }
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
            if opt.metadata["report_group"] == "WATCHLIST":
                opt.metadata["watchlist_reason"] = "NET_PROFIT_BELOW_THRESHOLD"
            else:
                opt.metadata.pop("watchlist_reason", None)
            # Tick density: downgrade to WATCHLIST if data quality is degraded
            if td_cfg.enabled and not td_cfg.shadow_mode_enabled:
                tick_quality = opt.metadata.get("tick_data_quality", "")
                if tick_quality and tick_quality not in {"OK", ""}:
                    opt.metadata["report_group"] = "WATCHLIST"
                    opt.metadata["watchlist_reason"] = "TICK_DATA_DEGRADED"
                    blocker_reason = normalize_readiness_blocker_code(
                        opt.metadata.get("readiness_blocker")
                    ) or readiness_blocker_from_tick_degradation_reason(
                        opt.metadata.get("tick_degradation_reason")
                    )
                    if blocker_reason:
                        opt.metadata["readiness_blocker"] = blocker_reason
            lower_tick, upper_tick = _parse_tick_range_from_metadata(opt.metadata)
            range_watchlist_reason = _range_watchlist_reason(lower_tick, upper_tick)
            if range_watchlist_reason is not None:
                opt.metadata["report_group"] = "WATCHLIST"
                opt.metadata["watchlist_reason"] = range_watchlist_reason
                blocker_reason = normalize_readiness_blocker_code(
                    opt.metadata.get("readiness_blocker")
                )
                if blocker_reason is None and td_cfg.enabled:
                    blocker_reason = _select_primary_readiness_blocker(
                        td_readiness_blockers
                    )
                if blocker_reason:
                    opt.metadata["readiness_blocker"] = blocker_reason
            net_profit_1k = (
                1000.0 * (opt.net_apy / 100.0) / 12.0
            ) - config.gas_efficiency.monthly_gas_cost_usd
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

        # Seed LP-entry eligibility state before StrategySim policy.
        # This keeps LP actionable decisions decoupled from generic
        # StrategySim downgrade reasons (PARTIAL/UNSUPPORTED/risk-profile).
        for pick in report_picks:
            pick.metadata["lp_entry_seed_report_group"] = str(
                pick.metadata.get("report_group") or "WATCHLIST"
            ).upper()
            pick.metadata["lp_entry_seed_watchlist_reason"] = str(
                pick.metadata.get("watchlist_reason") or ""
            ).upper()

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

        default_recommendation_top_n = int(
            getattr(config.reporting, "telegram_top_n_per_section", 0) or 5
        )
        lp_entry_target_cfg = config.lp_entry_targeting
        recommendation_top_n = int(
            lp_entry_target_cfg.top_n
            if lp_entry_target_cfg.enabled and lp_entry_target_cfg.top_n is not None
            else default_recommendation_top_n
        )
        lp_entry_cfg = config.lp_entry_calibration
        stability_min_observations = (
            int(lp_entry_cfg.stability_min_observations)
            if lp_entry_cfg.stability_enabled
            else 0
        )
        stability_observation_counts: dict[str, int] = {}
        if lp_entry_cfg.stability_enabled and report_picks:
            try:
                stability_observation_counts = compute_stability_observation_counts(
                    (pick.candidate.pool_id for pick in report_picks),
                    history_path=lp_entry_cfg.stability_history_path,
                    lookback_hours=lp_entry_cfg.stability_observation_window_hours,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LP entry stability history read degraded: reason=HISTORY_READ_ERROR err=%s",
                    exc.__class__.__name__,
                )
                stability_observation_counts = {}

        entry_input_total = len(report_picks)
        lp_entry_eligible_results, lp_entry_ineligible = split_lp_entry_eligibility(
            report_picks
        )
        entry_lp_eligible_total = len(lp_entry_eligible_results)
        entry_lp_ineligible_total = len(lp_entry_ineligible)

        entry_target_scope_enabled = int(lp_entry_target_cfg.enabled)
        entry_target_input_total = entry_lp_eligible_total + entry_lp_ineligible_total
        entry_target_matched_total = entry_target_input_total
        entry_target_excluded_total = 0
        entry_target_reason = "NONE"

        if lp_entry_target_cfg.enabled and (
            lp_entry_eligible_results or lp_entry_ineligible
        ):
            normalized_target_pair = normalize_pair_for_target_matching(
                lp_entry_target_cfg.target_pair
            )
            normalized_target_chains = {
                str(chain).strip().lower()
                for chain in (lp_entry_target_cfg.allowed_chains or [])
                if str(chain).strip()
            }
            normalized_target_projects = {
                re.sub(r"[\s_-]+", "", str(project).strip().lower())
                for project in (lp_entry_target_cfg.allowed_projects or [])
                if str(project).strip()
            }
            lp_entry_eligible_results = filter_lp_entry_target_scope(
                lp_entry_eligible_results,
                target_pair=lp_entry_target_cfg.target_pair,
                allowed_chains=lp_entry_target_cfg.allowed_chains,
                allowed_projects=lp_entry_target_cfg.allowed_projects,
            )
            lp_entry_ineligible = [
                (item, reason)
                for item, reason in lp_entry_ineligible
                if is_lp_entry_target_scope_match(
                    item,
                    normalized_target_pair=normalized_target_pair,
                    normalized_chains=normalized_target_chains,
                    normalized_projects=normalized_target_projects,
                )
            ]
            entry_target_matched_total = len(lp_entry_eligible_results) + len(
                lp_entry_ineligible
            )
            if entry_target_matched_total > entry_target_input_total:
                logger.warning(
                    "LP entry target telemetry mismatch: matched_total=%s exceeds input_total=%s; clamping.",
                    entry_target_matched_total,
                    entry_target_input_total,
                )
                entry_target_matched_total = entry_target_input_total
            entry_target_excluded_total = (
                entry_target_input_total - entry_target_matched_total
            )
            if entry_target_matched_total == 0:
                entry_target_reason = "TARGET_SCOPE_EMPTY"

        if lp_entry_target_cfg.enabled and entry_target_input_total == 0:
            entry_target_reason = "TARGET_SCOPE_EMPTY"

        entry_range_ready_total = 0
        entry_range_missing_total = 0
        for opt in lp_entry_eligible_results:
            lower_tick, upper_tick = _parse_tick_range_from_metadata(opt.metadata)
            range_reason = _range_watchlist_reason(lower_tick, upper_tick)
            if range_reason is None:
                entry_range_ready_total += 1
                continue
            entry_range_missing_total += 1
            opt.metadata["report_group"] = "WATCHLIST"
            opt.metadata["watchlist_reason"] = range_reason

        eligible_recommendations = build_entry_recommendations(
            lp_entry_eligible_results,
            top_n=max(1, recommendation_top_n),
            stability_observation_counts=stability_observation_counts,
            stability_min_observations=stability_min_observations,
            calibration=lp_entry_cfg,
        )
        ineligible_recommendations = build_ineligible_entry_recommendations(
            lp_entry_ineligible
        )
        entry_recommendations = eligible_recommendations + ineligible_recommendations
        topn_cache = CacheController(namespace="lp_entry_topn_stability")
        previous_topn_raw = topn_cache.get("topn_pool_ids")
        previous_topn_pool_ids = (
            previous_topn_raw
            if isinstance(previous_topn_raw, (list, tuple, set))
            else []
        )
        stability_telemetry = summarize_entry_stability_telemetry(
            entry_recommendations,
            top_n=max(1, recommendation_top_n),
            previous_topn_pool_ids=normalize_pool_ids(previous_topn_pool_ids),
        )
        watchlist_reason_counts = summarize_watchlist_reason_counts(
            entry_recommendations
        )
        watchlist_blocker_reason_counts = summarize_watchlist_blocker_reason_counts(
            entry_recommendations
        )
        topn_cache.set(
            "topn_pool_ids",
            stability_telemetry.topn_pool_ids,
            ttl_seconds=365 * 24 * 3600,
        )
        logger.info(
            "LP entry stability telemetry: entry_total=%s entry_actionable=%s entry_watchlist=%s "
            "entry_watchlist_insufficient_history=%s entry_topn_churn=%.4f "
            "entry_input_total=%s entry_lp_eligible_total=%s entry_lp_ineligible_total=%s "
            "entry_range_ready_total=%s entry_range_missing_total=%s "
            "entry_target_scope_enabled=%s entry_target_input_total=%s "
            "entry_target_matched_total=%s entry_target_excluded_total=%s "
            "entry_target_reason=%s watchlist_reason_counts=%s "
            "watchlist_blocker_reason_counts=%s",
            stability_telemetry.entry_total,
            stability_telemetry.entry_actionable,
            stability_telemetry.entry_watchlist,
            stability_telemetry.entry_watchlist_insufficient_history,
            stability_telemetry.entry_topn_churn,
            entry_input_total,
            entry_lp_eligible_total,
            entry_lp_ineligible_total,
            entry_range_ready_total,
            entry_range_missing_total,
            entry_target_scope_enabled,
            entry_target_input_total,
            entry_target_matched_total,
            entry_target_excluded_total,
            entry_target_reason,
            _format_reason_counts_for_log(watchlist_reason_counts),
            _format_reason_counts_for_log(watchlist_blocker_reason_counts),
        )

        # --- Execution loop (Spec 018, isolated and optional) ---
        if config.execution.enabled:
            states = await _load_execution_states(config)
            if not states:
                logger.info(
                    "Execution enabled but no valid position states available; loop skipped."
                )
            else:
                execution_orchestrator = ExecutionOrchestrator(
                    mode=config.execution.mode,
                    trigger_engine=TriggerEngine(config.execution),
                    policy_guard=PolicyGuard(config.execution.policy),
                    adapter=_build_execution_adapter(config),
                )
                execution_report = await execution_orchestrator.run_states(states)
                ec = execution_report.counters
                logger.info(
                    "Execution summary: mode=%s states=%s tx_plans=%s intents=%s blocked_by_policy=%s "
                    "sim_ok=%s sim_fail=%s exec_ok=%s exec_fail=%s "
                    "policy_blocks=%s sim_fail_reasons=%s exec_fail_reasons=%s",
                    execution_report.mode,
                    len(states),
                    len(execution_report.tx_plans),
                    ec.intent_count,
                    ec.blocked_by_policy,
                    ec.sim_ok,
                    ec.sim_fail,
                    ec.exec_ok,
                    ec.exec_fail,
                    execution_report.policy_block_reason_counts or {},
                    execution_report.sim_fail_reason_counts or {},
                    execution_report.exec_fail_reason_counts or {},
                )
        else:
            logger.info("Execution loop disabled.")

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

        actionable_count = sum(
            1
            for pick in report_picks
            if pick.metadata.get("report_group") == "ACTIONABLE"
        )
        watchlist_count = sum(
            1
            for pick in report_picks
            if pick.metadata.get("report_group") == "WATCHLIST"
        )
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
            poll_limit = int(
                getattr(config.reporting, "telegram_recheck_poll_limit", 20) or 20
            )
            command = str(
                getattr(config.reporting, "telegram_recheck_command", "/recheck")
                or "/recheck"
            )
            requests, next_offset = await notifier.fetch_recheck_requests(
                offset=offset,
                limit=poll_limit,
                command=command,
            )
            if next_offset is not None and next_offset != offset:
                recheck_cache.set(
                    "offset", int(next_offset), ttl_seconds=365 * 24 * 3600
                )

            # Bootstrap: first poll only advances offset and avoids replaying stale commands.
            if offset is None and requests:
                logger.info(
                    "Recheck command poll bootstrapped: skipped=%s (offset initialized=%s).",
                    len(requests),
                    next_offset,
                )
                requests = []

            threshold_pct = float(
                getattr(config.reporting, "telegram_recheck_change_threshold_pct", 20.0)
                or 20.0
            )
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

                current_net_1k = (
                    1000.0 * (float(candidate.apy or 0.0) / 100.0) / 12.0
                ) - config.gas_efficiency.monthly_gas_cost_usd
                baseline = shadow_tracker.latest_prediction(pool_id)
                baseline_value = None
                if isinstance(baseline, dict):
                    baseline_value = baseline.get("predicted_net_profit_1k")
                try:
                    baseline_net_1k = (
                        float(baseline_value) if baseline_value is not None else None
                    )
                except (TypeError, ValueError):
                    baseline_net_1k = None

                decision_line = (
                    "⚪ NEED_BASELINE — no prior shadow snapshot for this pool."
                )
                delta_line = "Δproxy: n/a"
                if baseline_net_1k is not None and abs(baseline_net_1k) > 1e-9:
                    delta_pct = (
                        abs(current_net_1k - baseline_net_1k)
                        / abs(baseline_net_1k)
                        * 100.0
                    )
                    delta_line = (
                        f"Δproxy: {delta_pct:.1f}% (threshold {threshold_pct:.1f}%)"
                    )
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
                            (
                                f"Baseline proxy Net@1k: {baseline_net_1k:.2f}/mo"
                                if baseline_net_1k is not None
                                else "Baseline proxy Net@1k: n/a"
                            ),
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
        if report_picks:
            div_stats = _freshness_divergence_stats(report_picks)
            for provider, (samples, apy_p50, apy_p90, tvl_p50, tvl_p90) in sorted(
                div_stats.items()
            ):
                if samples <= 0:
                    continue
                logger.info(
                    "Freshness divergence: provider=%s samples=%s apy_p50=%s apy_p90=%s tvl_p50=%s tvl_p90=%s",
                    provider,
                    samples,
                    f"{apy_p50:.2f}" if apy_p50 is not None else "n/a",
                    f"{apy_p90:.2f}" if apy_p90 is not None else "n/a",
                    f"{tvl_p50:.2f}" if tvl_p50 is not None else "n/a",
                    f"{tvl_p90:.2f}" if tvl_p90 is not None else "n/a",
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
                    entry_recommendations=entry_recommendations,
                )
                _mark_telegram_digest_sent()
                logger.info(
                    "Reported %s opportunities (safe=%s warn=%s actionable=%s watchlist=%s shadow=%s).",
                    len(report_picks),
                    len(safe_picks),
                    len(warn_picks),
                    actionable_count,
                    watchlist_count,
                    bool(
                        getattr(config.reporting, "telegram_shadow_mode_enabled", False)
                    ),
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
