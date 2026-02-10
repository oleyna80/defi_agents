import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.inspector.manager import ProtocolInspector
from defi_agents.inspector.report import format_inspector_report
from defi_agents.inspector.rpc import EvmRpcClient
from defi_agents.scout.config import ScoutConfig


@pytest.mark.asyncio
async def test_rpc_detect_proxy_decodes_slots():
    client = EvmRpcClient("https://example.invalid")
    impl = "0x0000000000000000000000001234567890abcdef1234567890abcdef12345678"
    admin = "0x000000000000000000000000abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    client.get_storage_at = AsyncMock(side_effect=[impl, admin])  # type: ignore[method-assign]

    is_proxy, implementation, admin_address = await client.detect_proxy(
        "0x1111111111111111111111111111111111111111"
    )

    assert is_proxy is True
    assert implementation == "0x1234567890abcdef1234567890abcdef12345678"
    assert admin_address == "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"


@pytest.mark.asyncio
async def test_inspector_partial_when_rpc_missing(tmp_path):
    config = ScoutConfig.model_validate(
        {
            "inspector": {
                "enabled": True,
                "output_dir": str(tmp_path),
                "targets": [
                    {
                        "target_id": "altura-hyperevm",
                        "chain": "HyperEVM",
                        "seed_addresses": ["0xd0Ee0CF300DFB598270cd7F4D0c6E0D8F6e13f29"],
                    }
                ],
            }
        }
    )
    inspector = ProtocolInspector(config)
    dossiers = await inspector.inspect()

    assert len(dossiers) == 1
    assert dossiers[0].status.value == "PARTIAL"
    assert dossiers[0].verdict.value == "WATCHLIST"
    assert "rpc_url" in dossiers[0].missing


@pytest.mark.asyncio
async def test_inspector_pass_with_seed_and_mocked_rpc(tmp_path, monkeypatch):
    class _FakeRpc:
        def __init__(self, rpc_url: str, timeout_seconds: int = 10) -> None:
            self.rpc_url = rpc_url
            self.timeout_seconds = timeout_seconds

        async def chain_id(self) -> int:
            return 999

        async def block_number(self) -> int:
            return 12345

        async def get_code(self, address: str) -> str:
            return "0x60006000"

        async def detect_proxy(self, address: str):
            return False, None, None

        async def read_owner(self, address: str):
            return "0x9999999999999999999999999999999999999999"

        async def read_paused(self, address: str):
            return False

    monkeypatch.setattr("defi_agents.inspector.manager.EvmRpcClient", _FakeRpc)

    config = ScoutConfig.model_validate(
        {
            "inspector": {
                "enabled": True,
                "output_dir": str(tmp_path),
                "rpc_urls": {"HyperEVM": "https://rpc.hyperliquid.xyz/evm"},
                "targets": [
                    {
                        "target_id": "altura-hyperevm",
                        "name": "Altura",
                        "chain": "HyperEVM",
                        "seed_addresses": ["0xd0Ee0CF300DFB598270cd7F4D0c6E0D8F6e13f29"],
                    }
                ],
            }
        }
    )
    inspector = ProtocolInspector(config)
    dossiers = await inspector.inspect()
    assert len(dossiers) == 1
    dossier = dossiers[0]
    assert dossier.status.value == "OK"
    assert dossier.verdict.value == "PASS"
    assert len(dossier.contracts) == 1
    assert dossier.contracts[0].owner == "0x9999999999999999999999999999999999999999"

    message = format_inspector_report(dossiers)
    assert "Protocol Inspector Report" in message
    assert "Verdict `PASS`" in message

