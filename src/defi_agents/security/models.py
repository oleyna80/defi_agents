from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SecuritySource(str, Enum):
    """Where a security signal came from (priority and semantics differ by source)."""

    WHITELIST = "whitelist"
    GOPLUS = "goplus"
    DEFI_LLAMA = "defi_llama"
    DEFI_REPUTATION = "defi_reputation"
    AGGREGATED = "aggregated"


class SecuritySeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityStatus(str, Enum):
    TRUSTED = "trusted"
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"
    UNKNOWN = "unknown"


class SecurityReason(BaseModel):
    """Machine-readable explanation for a decision."""

    code: str
    label: str
    severity: SecuritySeverity
    source: SecuritySource
    data: Dict[str, Any] = Field(default_factory=dict)


class SecuritySourceRecord(BaseModel):
    """A compact representation of raw-ish upstream data for traceability."""

    source: SecuritySource
    as_of: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Keep it small: a few identifiers/scores/flags, not full provider payloads.
    summary: Dict[str, Any] = Field(default_factory=dict)


class SecurityReputation(BaseModel):
    protocol_score: Optional[int] = None
    is_audited: Optional[bool] = None
    has_top_tier_audit: Optional[bool] = None
    has_tier_a_audit: Optional[bool] = None
    has_tier_b_audit: Optional[bool] = None
    has_low_reputation_audit: Optional[bool] = None
    rekt_history: Optional[bool] = None
    last_rekt_date: Optional[datetime] = None
    last_top_tier_audit_date: Optional[datetime] = None
    auditors: List[str] = Field(default_factory=list)
    protocol_slug: Optional[str] = None
    protocol_name: Optional[str] = None

    @staticmethod
    def unidentified_penalty(name: Optional[str]) -> "SecurityReputation":
        return SecurityReputation(
            protocol_score=None,
            is_audited=False,
            has_top_tier_audit=False,
            rekt_history=None,
            protocol_slug=None,
            protocol_name=name,
        )


class SecurityCandidate(BaseModel):
    """A token/protocol/pool to be screened."""

    chain_id: str
    address: str
    symbol: Optional[str] = None
    name: Optional[str] = None
    protocol: Optional[str] = None
    pool_id: Optional[str] = None


class SecurityConfig(BaseModel):
    tax_warn_pct: float = 10.0
    tax_block_pct: float = 20.0
    cache_ttl_seconds: int = 3600
    require_security_for_recommendation: bool = True
    fail_safe_unknown_non_tier1: bool = True


class SecurityResult(BaseModel):
    status: SecurityStatus
    score: int = Field(ge=0, le=100)
    reasons: List[SecurityReason] = Field(default_factory=list)
    sources: List[SecuritySourceRecord] = Field(default_factory=list)
    is_trusted: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: int = 0
    reputation: Optional[SecurityReputation] = None

    @staticmethod
    def trusted_from_whitelist(
        *,
        reason: str = "Found in docs/memory-bank/security/whitelist.json",
        data: Optional[Dict[str, Any]] = None,
    ) -> "SecurityResult":
        reason = SecurityReason(
            code="MANUAL_WHITELIST_MATCH",
            label=reason,
            severity=SecuritySeverity.NONE,
            source=SecuritySource.WHITELIST,
            data=data or {},
        )
        return SecurityResult(
            status=SecurityStatus.TRUSTED,
            score=100,
            reasons=[reason],
            sources=[
                SecuritySourceRecord(
                    source=SecuritySource.WHITELIST,
                    summary={"match": True},
                )
            ],
            is_trusted=True,
            ttl_seconds=0,
        )

    @staticmethod
    def pass_as_tier1(
        *,
        reason: str = "Tier 1 stable (hardcoded safe list)",
        data: Optional[Dict[str, Any]] = None,
    ) -> "SecurityResult":
        reason_obj = SecurityReason(
            code="TIER1_SAFE",
            label=reason,
            severity=SecuritySeverity.NONE,
            source=SecuritySource.AGGREGATED,
            data=data or {},
        )
        return SecurityResult(
            status=SecurityStatus.PASS,
            score=95,
            reasons=[reason_obj],
            sources=[
                SecuritySourceRecord(
                    source=SecuritySource.AGGREGATED,
                    summary={"tier1": True},
                )
            ],
            is_trusted=False,
            ttl_seconds=0,
        )

    @staticmethod
    def unknown_from_error(
        *,
        reason: str,
        source: SecuritySource = SecuritySource.GOPLUS,
        data: Optional[Dict[str, Any]] = None,
    ) -> "SecurityResult":
        reason_obj = SecurityReason(
            code="DATA_UNAVAILABLE",
            label=reason,
            severity=SecuritySeverity.MEDIUM,
            source=source,
            data=data or {},
        )
        return SecurityResult(
            status=SecurityStatus.UNKNOWN,
            score=0,
            reasons=[reason_obj],
            sources=[SecuritySourceRecord(source=source, summary={"error": True})],
            is_trusted=False,
            ttl_seconds=0,
        )

    def add_reason(
        self,
        *,
        code: str,
        label: str,
        severity: SecuritySeverity,
        source: SecuritySource,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.reasons.append(
            SecurityReason(
                code=code,
                label=label,
                severity=severity,
                source=source,
                data=data or {},
            )
        )

    def aggregate_reputation(self, reputation: SecurityReputation) -> None:
        """Enrich result with Stage B reputation data and adjust status."""
        self.reputation = reputation

        if reputation.rekt_history:
            # Amnesty rule: if incident > 24 months ago AND top-tier audit after incident => WARN, else BLOCK
            now = datetime.now(timezone.utc)
            is_old = False
            if reputation.last_rekt_date:
                months = (now.year - reputation.last_rekt_date.year) * 12 + (
                    now.month - reputation.last_rekt_date.month
                )
                is_old = months >= 24

            audit_after_incident = False
            if reputation.last_rekt_date and reputation.last_top_tier_audit_date:
                audit_after_incident = (
                    reputation.last_top_tier_audit_date > reputation.last_rekt_date
                )

            if is_old and audit_after_incident:
                if self.status != SecurityStatus.BLOCK:
                    self.status = SecurityStatus.WARN
                severity = SecuritySeverity.HIGH
                code = "PROTOCOL_REKT_HISTORY_AMNESTY"
                label = "Old exploit (24m+), fixed and re-audited"
            else:
                self.status = SecurityStatus.BLOCK
                severity = SecuritySeverity.CRITICAL
                code = "PROTOCOL_REKT_HISTORY"
                label = "Recent exploit (under 24m)"

            self.add_reason(
                code=code,
                label=label,
                severity=severity,
                source=SecuritySource.DEFI_REPUTATION,
            )

        auditors = [a.strip().lower() for a in reputation.auditors or []]
        has_tier_a = bool(reputation.has_tier_a_audit)
        has_tier_b = bool(reputation.has_tier_b_audit)
        has_low_rep = bool(reputation.has_low_reputation_audit)

        if has_tier_a:
            self.add_reason(
                code="TOP_TIER_AUDIT",
                label="Audited by Tier A firm(s)",
                severity=SecuritySeverity.LOW,
                source=SecuritySource.DEFI_REPUTATION,
            )
        elif has_tier_b:
            self.add_reason(
                code="TIER_B_AUDIT_ONLY",
                label="Audited by Tier B firm(s) only",
                severity=SecuritySeverity.LOW,
                source=SecuritySource.DEFI_REPUTATION,
            )
        elif has_low_rep:
            if self.status != SecurityStatus.BLOCK:
                self.status = SecurityStatus.WARN
            self.add_reason(
                code="LOW_REPUTATION_AUDITOR",
                label="Only CertiK audit found (low reputation)",
                severity=SecuritySeverity.MEDIUM,
                source=SecuritySource.DEFI_REPUTATION,
            )
        elif reputation.is_audited is False or auditors:
            if self.status != SecurityStatus.BLOCK:
                self.status = SecurityStatus.WARN
            self.add_reason(
                code="NO_AUDITS_FOUND",
                label="No audits found",
                severity=SecuritySeverity.MEDIUM,
                source=SecuritySource.DEFI_REPUTATION,
            )

        if reputation.protocol_score is not None:
            if reputation.protocol_score < 50:
                if self.status != SecurityStatus.BLOCK:
                    self.status = SecurityStatus.WARN
                self.add_reason(
                    code="LOW_PROTOCOL_SCORE",
                    label=f"Low protocol score ({reputation.protocol_score})",
                    severity=SecuritySeverity.HIGH,
                    source=SecuritySource.DEFI_REPUTATION,
                )
            elif 50 <= reputation.protocol_score < 70:
                if self.status == SecurityStatus.PASS:
                    self.status = SecurityStatus.WARN
                self.add_reason(
                    code="MEDIUM_PROTOCOL_SCORE",
                    label=f"Protocol score in yellow zone ({reputation.protocol_score})",
                    severity=SecuritySeverity.MEDIUM,
                    source=SecuritySource.DEFI_REPUTATION,
                )

        if reputation.has_top_tier_audit is False:
            if self.status != SecurityStatus.BLOCK:
                self.status = SecurityStatus.WARN
            self.add_reason(
                code="NO_TOP_TIER_AUDIT",
                label="No audits from Tier A/B firms found",
                severity=SecuritySeverity.MEDIUM,
                source=SecuritySource.DEFI_REPUTATION,
            )

        if reputation.protocol_slug is None and reputation.protocol_name:
            if self.status != SecurityStatus.BLOCK:
                self.status = SecurityStatus.WARN
            self.add_reason(
                code="UNIDENTIFIED_PROTOCOL",
                label=f"Protocol slug not resolved for {reputation.protocol_name}",
                severity=SecuritySeverity.MEDIUM,
                source=SecuritySource.DEFI_REPUTATION,
            )


# Back-compat: some modules may prefer string literals.
SecurityStatusLiteral = Literal["trusted", "pass", "warn", "block", "unknown"]
