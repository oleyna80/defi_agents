from __future__ import annotations

from typing import Iterable

from .models import InspectorDossier, InspectorSeverity


def _severity_icon(severity: InspectorSeverity) -> str:
    if severity == InspectorSeverity.CRITICAL:
        return "🔴"
    if severity == InspectorSeverity.HIGH:
        return "🟠"
    if severity == InspectorSeverity.MEDIUM:
        return "🟡"
    return "🔵"


def format_inspector_report(dossiers: Iterable[InspectorDossier]) -> str:
    lines = ["*Protocol Inspector Report*", ""]
    for dossier in dossiers:
        lines.append(
            f"*{dossier.protocol_name}* | `{dossier.chain}` | "
            f"Status `{dossier.status.value}` | Verdict `{dossier.verdict.value}`"
        )
        if dossier.rationale:
            lines.append(f"- Rationale: {dossier.rationale}")
        if dossier.block_number is not None:
            lines.append(f"- Block: `{dossier.block_number}`")
        lines.append(f"- Core contracts: `{len(dossier.contracts)}`")
        if dossier.missing:
            lines.append(f"- Missing: `{','.join(dossier.missing)}`")
        if dossier.diffs:
            lines.append(f"- Diffs: `{','.join(dossier.diffs)}`")
        for finding in dossier.findings[:5]:
            lines.append(f"- {_severity_icon(finding.severity)} `{finding.code}`: {finding.message}")
        lines.append("")
    return "\n".join(lines).strip()

