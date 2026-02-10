import asyncio
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from defi_agents.inspector.manager import ProtocolInspector
from defi_agents.inspector.report import format_inspector_report
from defi_agents.notifier import TelegramNotifier
from defi_agents.scout.config import ScoutConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ProtocolInspector")
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


async def run_protocol_inspector() -> None:
    _load_env_file()
    config = ScoutConfig.from_file("docs/memory-bank/scout_config.json")

    inspector = ProtocolInspector(config)
    dossiers = await inspector.inspect()
    if not dossiers:
        logger.info("No dossiers produced.")
        return

    for dossier in dossiers:
        logger.info(
            "Inspector dossier: target=%s status=%s verdict=%s contracts=%s findings=%s missing=%s diffs=%s",
            dossier.target_id,
            dossier.status.value,
            dossier.verdict.value,
            len(dossier.contracts),
            len(dossier.findings),
            len(dossier.missing),
            len(dossier.diffs),
        )

    notifier = TelegramNotifier(include_tags=False)
    message = format_inspector_report(dossiers)
    await notifier.send_markdown_report(message)
    logger.info("Protocol Inspector report sent: targets=%s", len(dossiers))


if __name__ == "__main__":
    try:
        asyncio.run(run_protocol_inspector())
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.critical("FATAL: Inspector crashed: %s", exc, exc_info=True)
        sys.exit(1)

