from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class InspectorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InspectorStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"


class InspectorVerdict(str, Enum):
    PASS = "PASS"
    WATCHLIST = "WATCHLIST"
    FAIL = "FAIL"


class InspectorContract(BaseModel):
    address: str
    label: str = "core"
    code_hash: str = ""
    is_proxy: bool = False
    implementation: str | None = None
    admin: str | None = None
    owner: str | None = None
    paused: bool | None = None


class InspectorFinding(BaseModel):
    code: str
    severity: InspectorSeverity
    message: str
    data: dict = Field(default_factory=dict)


class InspectorEvidence(BaseModel):
    source: str
    reference: str
    details: dict = Field(default_factory=dict)


class InspectorDossier(BaseModel):
    target_id: str
    protocol_name: str
    chain: str
    chain_id: int | None = None
    status: InspectorStatus = InspectorStatus.PARTIAL
    verdict: InspectorVerdict = InspectorVerdict.WATCHLIST
    rationale: str = ""
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    block_number: int | None = None
    contracts: List[InspectorContract] = Field(default_factory=list)
    findings: List[InspectorFinding] = Field(default_factory=list)
    missing: List[str] = Field(default_factory=list)
    evidence: List[InspectorEvidence] = Field(default_factory=list)
    diffs: List[str] = Field(default_factory=list)

