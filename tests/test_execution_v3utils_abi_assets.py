import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_v3utils_abi_bundle_files_exist_and_parse():
    abi_dir = ROOT / "src" / "defi_agents" / "execution" / "abi"
    files = [
        abi_dir / "v3utils_execute.abi.json",
        abi_dir / "v3automation_execute.abi.json",
        abi_dir / "v3utils_contracts.json",
        abi_dir / "v3utils.lock.json",
    ]
    for path in files:
        assert path.exists(), f"missing ABI bundle file: {path}"
        _load_json(path)


def test_v3utils_execute_abi_has_execute_entrypoint():
    abi_path = ROOT / "src" / "defi_agents" / "execution" / "abi" / "v3utils_execute.abi.json"
    abi = _load_json(abi_path)
    execute_items = [item for item in abi if item.get("type") == "function" and item.get("name") == "execute"]
    assert len(execute_items) == 1
    assert execute_items[0].get("stateMutability") == "nonpayable"


def test_v3automation_abi_has_execute_and_order_helpers():
    abi_path = ROOT / "src" / "defi_agents" / "execution" / "abi" / "v3automation_execute.abi.json"
    abi = _load_json(abi_path)
    names = {item.get("name") for item in abi if item.get("type") == "function"}
    assert {"execute", "cancelOrder", "isOrderCancelled"}.issubset(names)


def test_v3utils_lock_commit_matches_expected():
    lock_path = ROOT / "src" / "defi_agents" / "execution" / "abi" / "v3utils.lock.json"
    payload = _load_json(lock_path)
    assert payload["upstream_repo"] == "https://github.com/KrystalDeFi/v3utils"
    assert payload["upstream_commit"] == "33f487253051c3d6f439dc911b0e415b28b4cc9c"
