from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from ..scout.config import InspectorConfig, InspectorTargetConfig, ScoutConfig
from .models import (
    InspectorContract,
    InspectorDossier,
    InspectorEvidence,
    InspectorFinding,
    InspectorSeverity,
    InspectorStatus,
    InspectorVerdict,
)
from .rpc import EvmRpcClient, code_hash
from .storage import DossierStorage

logger = logging.getLogger("ProtocolInspector")


def _safe_url(value: str) -> str:
    return re.sub(r"/api/[^/]+/", "/api/***/", value)


class ProtocolInspector:
    def __init__(self, scout_config: ScoutConfig) -> None:
        self.scout_config = scout_config
        self.config: InspectorConfig = scout_config.inspector
        self.storage = DossierStorage(self.config.output_dir)
        self._http_requests = 0

    def _resolve_rpc_url(self, target: InspectorTargetConfig) -> str | None:
        if target.rpc_url:
            return target.rpc_url
        if target.chain in self.config.rpc_urls:
            return self.config.rpc_urls[target.chain]
        return None

    def _resolve_chain_id(self, target: InspectorTargetConfig) -> int | None:
        if target.chain_id is not None:
            return target.chain_id
        return self.scout_config.chain_id_map.get(target.chain)

    async def _fetch_json(self, url: str) -> dict[str, Any] | None:
        if self._http_requests >= self.config.budgets.max_http_requests:
            return None
        self._http_requests += 1
        try:
            async with httpx.AsyncClient(timeout=float(self.config.timeout_seconds)) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except Exception:
            logger.warning("Inspector source fetch failed: %s", _safe_url(url.split("?")[0]))
            return None

    def _extract_addresses_from_llama_pool(self, payload: dict[str, Any]) -> list[str]:
        items: list[str] = []
        data = payload.get("data", payload)
        if isinstance(data, dict):
            for key in ("address", "poolAddress", "vault", "contract", "pool_old"):
                value = data.get(key)
                if isinstance(value, str) and value.startswith("0x") and len(value) == 42:
                    items.append(value.lower())
        return items

    async def _resolve_seed_addresses(self, target: InspectorTargetConfig, dossier: InspectorDossier) -> list[str]:
        addresses = [addr.lower() for addr in target.seed_addresses if addr.startswith("0x") and len(addr) == 42]
        if addresses:
            dossier.evidence.append(
                InspectorEvidence(source="seed_addresses", reference="config", details={"count": len(addresses)})
            )
            return sorted(set(addresses))

        pool_id = target.defillama_yield_pool_id
        if pool_id:
            pool_payload = await self._fetch_json(f"https://yields.llama.fi/pool/{pool_id}")
            if pool_payload:
                addresses.extend(self._extract_addresses_from_llama_pool(pool_payload))
                dossier.evidence.append(
                    InspectorEvidence(source="defillama_pool", reference=pool_id, details={"resolved": len(addresses)})
                )

            legacy_payload = await self._fetch_json(f"https://yields.llama.fi/poolsOld/{pool_id}")
            if legacy_payload:
                addresses.extend(self._extract_addresses_from_llama_pool(legacy_payload))
                dossier.evidence.append(
                    InspectorEvidence(
                        source="defillama_poolsOld",
                        reference=pool_id,
                        details={"resolved": len(addresses)},
                    )
                )

        return sorted(set(addresses))

    async def _inspect_contract(self, rpc: EvmRpcClient, address: str) -> tuple[InspectorContract | None, list[InspectorFinding]]:
        findings: list[InspectorFinding] = []
        try:
            code = await rpc.get_code(address)
            if not code or code in {"0x", "0X"}:
                findings.append(
                    InspectorFinding(
                        code="NO_CODE",
                        severity=InspectorSeverity.HIGH,
                        message=f"Address has no contract code: {address}",
                    )
                )
                return None, findings
            contract = InspectorContract(address=address, code_hash=code_hash(code))
        except Exception as exc:  # noqa: BLE001
            findings.append(
                InspectorFinding(
                    code="RPC_CODE_ERROR",
                    severity=InspectorSeverity.HIGH,
                    message=f"Failed to read contract code for {address}: {exc.__class__.__name__}",
                )
            )
            return None, findings

        try:
            is_proxy, implementation, admin = await rpc.detect_proxy(address)
            contract.is_proxy = is_proxy
            contract.implementation = implementation
            contract.admin = admin
            if is_proxy and implementation is None:
                findings.append(
                    InspectorFinding(
                        code="PROXY_IMPL_MISSING",
                        severity=InspectorSeverity.CRITICAL,
                        message=f"Proxy detected without implementation for {address}",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            findings.append(
                InspectorFinding(
                    code="RPC_PROXY_ERROR",
                    severity=InspectorSeverity.MEDIUM,
                    message=f"Proxy detection failed for {address}: {exc.__class__.__name__}",
                )
            )

        try:
            owner = await rpc.read_owner(address)
            contract.owner = owner
            if owner is None:
                findings.append(
                    InspectorFinding(
                        code="OWNER_UNAVAILABLE",
                        severity=InspectorSeverity.MEDIUM,
                        message=f"owner() not available or unreadable for {address}",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            findings.append(
                InspectorFinding(
                    code="RPC_OWNER_ERROR",
                    severity=InspectorSeverity.MEDIUM,
                    message=f"Failed to read owner for {address}: {exc.__class__.__name__}",
                )
            )

        try:
            paused = await rpc.read_paused(address)
            contract.paused = paused
            if paused is True:
                findings.append(
                    InspectorFinding(
                        code="CONTRACT_PAUSED",
                        severity=InspectorSeverity.HIGH,
                        message=f"Contract is paused: {address}",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            findings.append(
                InspectorFinding(
                    code="RPC_PAUSED_ERROR",
                    severity=InspectorSeverity.LOW,
                    message=f"Failed to read paused() for {address}: {exc.__class__.__name__}",
                )
            )

        return contract, findings

    def _derive_verdict(self, dossier: InspectorDossier) -> None:
        if dossier.missing:
            dossier.status = InspectorStatus.PARTIAL
        else:
            dossier.status = InspectorStatus.OK

        has_critical = any(f.severity == InspectorSeverity.CRITICAL for f in dossier.findings)
        if has_critical:
            dossier.verdict = InspectorVerdict.FAIL
            dossier.rationale = "Critical control risk detected."
            return

        if dossier.status == InspectorStatus.PARTIAL or dossier.findings:
            dossier.verdict = InspectorVerdict.WATCHLIST
            dossier.rationale = "Incomplete or non-critical risks detected; manual review required."
            return

        dossier.verdict = InspectorVerdict.PASS
        dossier.rationale = "Core onchain checks passed with no material findings."

    async def inspect_target(self, target: InspectorTargetConfig) -> InspectorDossier:
        protocol_name = target.name or target.defillama_protocol_slug or target.target_id
        dossier = InspectorDossier(
            target_id=target.target_id,
            protocol_name=protocol_name,
            chain=target.chain,
            chain_id=self._resolve_chain_id(target),
        )

        if target.defillama_protocol_slug and not target.name:
            protocol_payload = await self._fetch_json(
                f"https://api.llama.fi/protocol/{target.defillama_protocol_slug}"
            )
            if protocol_payload:
                dossier.protocol_name = str(protocol_payload.get("name") or dossier.protocol_name)
                dossier.evidence.append(
                    InspectorEvidence(
                        source="defillama_protocol",
                        reference=target.defillama_protocol_slug,
                        details={"tvl": protocol_payload.get("tvl")},
                    )
                )

        rpc_url = self._resolve_rpc_url(target)
        if not rpc_url:
            dossier.missing.append("rpc_url")
            dossier.findings.append(
                InspectorFinding(
                    code="RPC_MISSING",
                    severity=InspectorSeverity.HIGH,
                    message=f"RPC URL is not configured for chain {target.chain}",
                )
            )
            self._derive_verdict(dossier)
            saved = self.storage.save(target.target_id, dossier.model_dump(mode="json"))
            dossier.diffs = saved.diffs
            return dossier

        rpc = EvmRpcClient(rpc_url=rpc_url, timeout_seconds=self.config.timeout_seconds)
        try:
            chain_id = await rpc.chain_id()
            dossier.chain_id = chain_id
            dossier.block_number = await rpc.block_number()
        except Exception as exc:  # noqa: BLE001
            dossier.missing.append("rpc_connectivity")
            dossier.findings.append(
                InspectorFinding(
                    code="RPC_UNAVAILABLE",
                    severity=InspectorSeverity.HIGH,
                    message=f"RPC connectivity failed: {exc.__class__.__name__}",
                )
            )
            self._derive_verdict(dossier)
            saved = self.storage.save(target.target_id, dossier.model_dump(mode="json"))
            dossier.diffs = saved.diffs
            return dossier

        seed_addresses = await self._resolve_seed_addresses(target, dossier)
        if not seed_addresses:
            dossier.missing.append("core_contract_addresses")
            dossier.findings.append(
                InspectorFinding(
                    code="CONTRACT_SET_UNRESOLVED",
                    severity=InspectorSeverity.HIGH,
                    message="Unable to resolve core contract addresses from configured sources.",
                )
            )
            self._derive_verdict(dossier)
            saved = self.storage.save(target.target_id, dossier.model_dump(mode="json"))
            dossier.diffs = saved.diffs
            return dossier

        rpc_budget = self.config.budgets.max_rpc_calls
        rpc_spent = 0
        for address in seed_addresses:
            if rpc_spent >= rpc_budget:
                dossier.missing.append("rpc_budget_exceeded")
                break
            contract, findings = await self._inspect_contract(rpc, address)
            dossier.findings.extend(findings)
            rpc_spent += 8
            if contract is not None:
                dossier.contracts.append(contract)

        if not dossier.contracts:
            dossier.missing.append("valid_core_contracts")

        self._derive_verdict(dossier)
        payload = dossier.model_dump(mode="json")
        saved = self.storage.save(target.target_id, payload)
        dossier.diffs = saved.diffs
        return dossier

    async def inspect(self) -> list[InspectorDossier]:
        if not self.config.enabled:
            logger.info("Protocol Inspector disabled.")
            return []

        dossiers: list[InspectorDossier] = []
        max_targets = max(1, int(self.config.budgets.max_targets_per_run))
        for target in self.config.targets[:max_targets]:
            dossier = await self.inspect_target(target)
            dossiers.append(dossier)
        return dossiers
