from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from .models import SecurityResult


DEFAULT_WHITELIST_PATH = "docs/memory-bank/security/whitelist.json"


def _normalize_address(address: str) -> str:
    # Strip chain prefixes and normalize case.
    # Examples: "avax:0x..." -> "0x...", "0x..." -> "0x..."
    addr = address.strip().lower()
    if ":" in addr:
        addr = addr.split(":", 1)[1]
    return addr


class WhitelistProvider:
    """Lazy-loading provider for manual approvals (SSOT)."""

    def __init__(self, file_path: str = DEFAULT_WHITELIST_PATH) -> None:
        self.file_path = Path(file_path)
        self._data: Dict[str, Any] = {}
        self._mtime: Optional[float] = None

    def _load_data(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            self._data = {}
            self._mtime = None
            return self._data
        try:
            self._data = json.loads(self.file_path.read_text())
            self._mtime = self.file_path.stat().st_mtime
        except (json.JSONDecodeError, OSError):
            # Malformed JSON or read error -> treat as empty whitelist.
            self._data = {}
        return self._data

    def _maybe_reload(self) -> None:
        if not self.file_path.exists():
            self._data = {}
            self._mtime = None
            return
        mtime = self.file_path.stat().st_mtime
        if self._mtime is None or mtime != self._mtime:
            self._load_data()

    def check(self, address: str, chain_id: str) -> Optional[SecurityResult]:
        """Return TRUSTED SecurityResult if token/protocol is whitelisted, else None."""
        self._maybe_reload()
        data = self._data or {}
        approvals = data.get("manual_approvals", {})
        tokens = approvals.get("tokens", {})
        protocols = approvals.get("protocols", {})

        target_address = _normalize_address(address)
        if target_address in tokens:
            entry = tokens.get(target_address, {})
            reason = f"Whitelist match: {entry.get('symbol', 'N/A')} - {entry.get('reason')}"
            return SecurityResult.trusted_from_whitelist(reason=reason, data=entry)

        # Optional protocol lookup by chain_id if provided (address-like protocol ids).
        proto_key = _normalize_address(chain_id) if chain_id else ""
        if proto_key and proto_key in protocols:
            entry = protocols.get(proto_key, {})
            reason = f"Whitelist match: {entry.get('name', 'N/A')} - {entry.get('reason')}"
            return SecurityResult.trusted_from_whitelist(reason=reason, data=entry)

        return None
