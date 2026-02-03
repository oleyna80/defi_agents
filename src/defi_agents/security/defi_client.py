from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import httpx

from .models import SecurityReputation


PROTOCOL_CACHE_PATH = Path("docs/memory-bank/security/defi_protocols.json")
AUDIT_TIERS_PATH = Path("docs/memory-bank/security/audit_tiers.json")

TIER_A = {"openzeppelin", "trail of bits", "spearbit", "zellic"}
TIER_B = {"consensys diligence", "sigma prime", "nethermind", "chainsecurity"}
LOW_REPUTATION = {"certik"}
EXCLUDED_SUFFICIENT = {"quantstamp", "halborn"}


def _slugify(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class DeFiClient:
    BASE_URL = "https://api.de.fi"

    def __init__(self, timeout_seconds: float = 10.0, semaphore=None) -> None:
        self._timeout = timeout_seconds
        self._slug_cache: Dict[str, str] = {}
        self._loaded = False
        self._tiers_loaded = False
        self._sem = semaphore
        self._api_key = os.getenv("DEFI_API_KEY") or os.getenv("DEFI_API_TOKEN")

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._api_key:
            # Keep both for compatibility across De.Fi gateway variants.
            headers["X-API-Key"] = self._api_key
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _load_protocol_cache(self) -> None:
        if self._loaded:
            return
        if not PROTOCOL_CACHE_PATH.exists():
            self._loaded = True
            return
        try:
            data = json.loads(PROTOCOL_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            self._loaded = True
            return

        # Accept formats: {"protocols":[{"slug":...,"name":...}, ...]} or {"slug": "name", ...}
        if isinstance(data, dict) and "protocols" in data:
            for item in data.get("protocols", []):
                slug = str(item.get("slug", "")).strip()
                name = str(item.get("name", "")).strip()
                if slug:
                    self._slug_cache[slug] = name
                    self._slug_cache[_slugify(name)] = slug
        elif isinstance(data, dict):
            for slug, name in data.items():
                slug = str(slug).strip()
                name = str(name).strip()
                if slug:
                    self._slug_cache[slug] = name
                    self._slug_cache[_slugify(name)] = slug
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    self._slug_cache[item] = item
                elif isinstance(item, dict):
                    slug = str(item.get("slug", "")).strip()
                    name = str(item.get("name", "")).strip()
                    if slug:
                        self._slug_cache[slug] = name
                        self._slug_cache[_slugify(name)] = slug

        self._loaded = True

    def _load_audit_tiers(self) -> None:
        if self._tiers_loaded:
            return
        if not AUDIT_TIERS_PATH.exists():
            self._tiers_loaded = True
            return
        try:
            data = json.loads(AUDIT_TIERS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            self._tiers_loaded = True
            return

        def _norm(items: Iterable[str]) -> set[str]:
            return {str(i).strip().lower() for i in items if str(i).strip()}

        if isinstance(data, dict):
            global TIER_A, TIER_B, LOW_REPUTATION, EXCLUDED_SUFFICIENT
            TIER_A = _norm(data.get("tier_a", [])) or TIER_A
            TIER_B = _norm(data.get("tier_b", [])) or TIER_B
            LOW_REPUTATION = _norm(data.get("low_reputation", [])) or LOW_REPUTATION
            EXCLUDED_SUFFICIENT = _norm(data.get("excluded_as_sufficient", [])) or EXCLUDED_SUFFICIENT
        self._tiers_loaded = True

    def _try_find_slug_by_name(self, protocol_name: str) -> Optional[str]:
        self._load_protocol_cache()
        slug_guess = _slugify(protocol_name)
        if slug_guess in self._slug_cache:
            value = self._slug_cache[slug_guess]
            # If mapping stored as slug->name, return slug_guess; if name->slug, return value.
            if value and value != slug_guess and value in self._slug_cache:
                return value
            return slug_guess
        return None

    async def get_reputation(self, address: str) -> SecurityReputation:
        self._load_audit_tiers()
        scan_res = await self._fetch_scan(address)
        slug = scan_res.get("protocol_slug")
        name = scan_res.get("protocol_name")

        # Option 2: lookup by name if slug missing
        if not slug and name:
            slug = self._try_find_slug_by_name(name)
            if slug:
                audit_res = await self._fetch_audit_db(slug)
                return self._map_to_reputation(scan_res, audit_res, slug)

        if not slug:
            return SecurityReputation.unidentified_penalty(name)

        audit_res = await self._fetch_audit_db(slug)
        return self._map_to_reputation(scan_res, audit_res, slug)

    async def _fetch_scan(self, address: str) -> Dict[str, Any]:
        # Placeholder endpoints; adjust to actual De.Fi API routes.
        url = f"{self.BASE_URL}/scanner/{address}"
        if self._sem:
            async with self._sem:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, headers=self._headers())
                    resp.raise_for_status()
                    return resp.json()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    async def _fetch_audit_db(self, protocol_slug: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/audit/{protocol_slug}"
        if self._sem:
            async with self._sem:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(url, headers=self._headers())
                    resp.raise_for_status()
                    return resp.json()

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def _map_to_reputation(
        self, scan_res: Dict[str, Any], audit_res: Dict[str, Any], slug: str
    ) -> SecurityReputation:
        protocol_score = scan_res.get("protocol_score")
        protocol_name = scan_res.get("protocol_name")
        rekt_history = scan_res.get("rekt_history")

        audits = audit_res.get("audits", []) if isinstance(audit_res, dict) else []
        auditors = {str(a.get("auditor", "")).strip().lower() for a in audits}
        is_audited = bool(audits)
        has_tier_a = bool(auditors & TIER_A)
        has_tier_b = bool(auditors & TIER_B)
        has_top_tier = has_tier_a or has_tier_b

        # Optional: detect low-reputation-only audits
        has_low_rep = bool(auditors & LOW_REPUTATION)
        if auditors and not has_top_tier and has_low_rep:
            has_top_tier = False

        # Last dates (best-effort)
        def _parse_date(val: Any) -> Optional[datetime]:
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val)
                except ValueError:
                    return None
            return None

        last_rekt_date = _parse_date(scan_res.get("last_rekt_date"))
        last_top_tier_audit_date = None
        if audits:
            # pick latest audit date among tier A/B auditors (if present)
            top_audits = [
                a for a in audits if str(a.get("auditor", "")).strip().lower() in (TIER_A | TIER_B)
            ]
            dates = [_parse_date(a.get("date")) for a in top_audits]
            dates = [d for d in dates if d is not None]
            if dates:
                last_top_tier_audit_date = max(dates)

        return SecurityReputation(
            protocol_score=protocol_score if isinstance(protocol_score, int) else None,
            is_audited=is_audited,
            has_top_tier_audit=has_top_tier,
            has_tier_a_audit=has_tier_a,
            has_tier_b_audit=has_tier_b,
            has_low_reputation_audit=has_low_rep,
            rekt_history=bool(rekt_history) if rekt_history is not None else None,
            last_rekt_date=last_rekt_date,
            last_top_tier_audit_date=last_top_tier_audit_date,
            auditors=sorted(auditors),
            protocol_slug=slug,
            protocol_name=protocol_name,
        )
