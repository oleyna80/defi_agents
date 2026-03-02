import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.tracker.position_baseline import (  # noqa: E402
    ENTRY_BASELINE_INCOMPLETE,
    ENTRY_BASELINE_MALFORMED,
    ENTRY_BASELINE_MISSING,
    FileBackedPositionBaselineProvider,
)


def test_file_backed_baseline_provider_present(tmp_path: Path):
    path = tmp_path / "position_entry_baselines.json"
    payload = {
        "positions": {
            "uni-v3:1": {
                "entry_token0_amount": 100.0,
                "entry_token1_amount": 0.05,
                "entry_price_token0_usd": 1.0,
                "entry_price_token1_usd": 3000.0,
            }
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    provider = FileBackedPositionBaselineProvider(path)
    lookup = provider.lookup("uni-v3:1")

    assert lookup.reason_code is None
    assert lookup.baseline is not None
    assert lookup.baseline.position_ref == "uni-v3:1"
    assert lookup.baseline.entry_value_usd == 250.0


def test_file_backed_baseline_provider_missing_file_is_safe(tmp_path: Path):
    provider = FileBackedPositionBaselineProvider(tmp_path / "not_exists.json")

    lookup = provider.lookup("uni-v3:1")

    assert lookup.baseline is None
    assert lookup.reason_code == ENTRY_BASELINE_MISSING


def test_file_backed_baseline_provider_malformed_file(tmp_path: Path):
    path = tmp_path / "position_entry_baselines.json"
    path.write_text("{bad_json", encoding="utf-8")
    provider = FileBackedPositionBaselineProvider(path)

    lookup = provider.lookup("uni-v3:1")

    assert lookup.baseline is None
    assert lookup.reason_code == ENTRY_BASELINE_MALFORMED


def test_file_backed_baseline_provider_incomplete_entry(tmp_path: Path):
    path = tmp_path / "position_entry_baselines.json"
    payload = {
        "positions": {
            "uni-v3:1": {
                "entry_token0_amount": 100.0,
                "entry_price_token0_usd": 1.0,
                "entry_price_token1_usd": 3000.0,
            }
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    provider = FileBackedPositionBaselineProvider(path)

    lookup = provider.lookup("uni-v3:1")

    assert lookup.baseline is None
    assert lookup.reason_code == ENTRY_BASELINE_INCOMPLETE
