import asyncio
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from defi_agents.hedger import (
    HedgeCalculator,
    HedgeExposure,
    HedgerOrchestrator,
    HummingbotShadowConnector,
)
from defi_agents.scout.config import ScoutConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Hedger")
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
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _format_reason_counts(values: dict[str, int]) -> str:
    if not values:
        return "-"
    parts = [f"{k}={values[k]}" for k in sorted(values)]
    return ",".join(parts)


def _load_mock_exposures(raw_items: list[dict]) -> list[HedgeExposure]:
    exposures: list[HedgeExposure] = []
    now_ts = int(time.time())
    for idx, raw in enumerate(raw_items):
        item = dict(raw)
        if int(item.get("snapshot_ts", 0) or 0) <= 0:
            item["snapshot_ts"] = now_ts
        try:
            exposures.append(HedgeExposure(**item))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip invalid hedger mock exposure idx=%s err=%s", idx, exc.__class__.__name__)
    return exposures


async def run_hedger_cycle() -> None:
    _load_env_file()
    config = ScoutConfig.from_file("docs/memory-bank/scout_config.json")
    hedger_cfg = config.hedger

    if not hedger_cfg.enabled:
        logger.info("Hedger disabled via config (hedger.enabled=false)")
        return

    exposures = _load_mock_exposures(hedger_cfg.mock_exposures)
    if not exposures:
        logger.info("Hedger summary: mode=%s exposures=0 intents_hedge=0 intents_hold=0 intents_skip=0 sim_ok=0 sim_fail=0 connector_errors=0", hedger_cfg.mode)
        logger.info("Hedger note: no valid mock_exposures configured")
        return

    calculator = HedgeCalculator(hedger_cfg)
    connector = None
    if hedger_cfg.connector == "hummingbot":
        connector = HummingbotShadowConnector(
            base_url=hedger_cfg.hummingbot_base_url,
            timeout_seconds=hedger_cfg.connector_timeout_seconds,
            api_key=os.getenv(hedger_cfg.hummingbot_api_key_env, ""),
            exchange=hedger_cfg.hummingbot_exchange,
            market_map=hedger_cfg.hummingbot_market_map,
            health_path=hedger_cfg.hummingbot_health_path,
            markets_path=hedger_cfg.hummingbot_markets_path,
            ticker_path=hedger_cfg.hummingbot_ticker_path,
        )

    orchestrator = HedgerOrchestrator(
        mode=hedger_cfg.mode,
        calculator=calculator,
        connector=connector,
    )
    report = await orchestrator.run_exposures(exposures, now_ts=int(time.time()))
    logger.info(
        "Hedger summary: mode=%s exposures=%d intents_hedge=%d intents_hold=%d intents_skip=%d sim_ok=%d sim_fail=%d connector_errors=%d",
        report.mode,
        report.counters.exposures_seen,
        report.counters.intents_hedge,
        report.counters.intents_hold,
        report.counters.intents_skip,
        report.sim_ok,
        report.sim_fail,
        report.counters.connector_errors,
    )
    logger.info(
        "Hedger reasons: sim_fail=%s connector=%s",
        _format_reason_counts(report.sim_fail_reason_counts),
        _format_reason_counts(report.connector_reason_counts),
    )


if __name__ == "__main__":
    try:
        asyncio.run(run_hedger_cycle())
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.critical("FATAL: Hedger crashed: %s", exc, exc_info=True)
        sys.exit(1)

