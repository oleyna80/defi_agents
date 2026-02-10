from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class StorageResult:
    diffs: list[str]
    latest_path: Path
    previous_path: Path | None


def _extract_contract_index(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    contracts = data.get("contracts", [])
    index: dict[str, dict[str, Any]] = {}
    for contract in contracts:
        address = str(contract.get("address", "")).lower()
        if address:
            index[address] = contract
    return index


def _compute_high_impact_diffs(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    prev_index = _extract_contract_index(previous)
    cur_index = _extract_contract_index(current)
    all_addresses = sorted(set(prev_index.keys()) | set(cur_index.keys()))
    for address in all_addresses:
        prev = prev_index.get(address)
        cur = cur_index.get(address)
        if prev is None and cur is not None:
            diffs.append(f"contract_added:{address}")
            continue
        if prev is not None and cur is None:
            diffs.append(f"contract_removed:{address}")
            continue
        assert prev is not None and cur is not None
        for field in ("implementation", "admin", "owner", "paused"):
            old = prev.get(field)
            new = cur.get(field)
            if old != new:
                diffs.append(f"{field}_changed:{address}")
    return diffs


class DossierStorage:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _target_dir(self, target_id: str) -> Path:
        path = self.base_dir / target_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save(self, target_id: str, payload: dict[str, Any]) -> StorageResult:
        target_dir = self._target_dir(target_id)
        latest_path = target_dir / "latest.json"
        previous_path = target_dir / "prev.json"

        previous_payload: dict[str, Any] | None = None
        if latest_path.exists():
            previous_payload = json.loads(latest_path.read_text())
            previous_path.write_text(json.dumps(previous_payload, indent=2, ensure_ascii=True))

        diffs = _compute_high_impact_diffs(previous_payload or {}, payload)
        latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True))

        return StorageResult(
            diffs=diffs,
            latest_path=latest_path,
            previous_path=previous_path if previous_path.exists() else None,
        )

