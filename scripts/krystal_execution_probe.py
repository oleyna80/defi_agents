#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass
class ProbeResult:
    method: str
    path: str
    status_code: int | None
    ok: bool
    error: str | None
    body_preview: str


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _preview(text: str, limit: int = 200) -> str:
    clean = " ".join(text.split())
    return clean[:limit]


async def _probe_one(
    client: httpx.AsyncClient,
    *,
    method: str,
    base_url: str,
    path: str,
    headers: dict[str, str],
    payload: dict[str, Any] | None = None,
) -> ProbeResult:
    url = f"{base_url}{path}"
    try:
        response = await client.request(method, url, headers=headers, json=payload)
        body = response.text or ""
        return ProbeResult(
            method=method,
            path=path,
            status_code=response.status_code,
            ok=response.status_code < 400,
            error=None,
            body_preview=_preview(body),
        )
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(
            method=method,
            path=path,
            status_code=None,
            ok=False,
            error=exc.__class__.__name__,
            body_preview="",
        )


async def _run_probe(args: argparse.Namespace) -> int:
    base_url = args.base_url.rstrip("/")
    api_key = (os.getenv(args.api_key_env, "") or "").strip()
    headers = {
        "KC-APIKey": api_key,
        "Content-Type": "application/json",
    }

    if not api_key:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"missing_api_key_env:{args.api_key_env}",
                    "base_url": base_url,
                },
                indent=2,
            )
        )
        return 1

    chain_slug = args.chain
    probes: list[tuple[str, str, dict[str, Any] | None]] = [
        ("GET", f"/v1/pools?chainId={args.chain_id}&limit=1", None),
        (
            "POST",
            "/v1/execution/compound/build",
            {
                "intentId": "probe-compound",
                "action": "COMPOUND",
                "chain": chain_slug,
                "positionRef": "probe-position",
                "expectedNetUsd": 1.0,
                "metadata": {},
            },
        ),
        (
            "POST",
            "/v1/execution/rebalance/build",
            {
                "intentId": "probe-rebalance",
                "action": "REBALANCE",
                "chain": chain_slug,
                "positionRef": "probe-position",
                "expectedNetUsd": 1.0,
                "metadata": {},
            },
        ),
        (
            "POST",
            "/v1/execution/simulate",
            {
                "chain": chain_slug,
                "tx": {
                    "to": "0x1111111111111111111111111111111111111111",
                    "data": "0x",
                    "value": "0",
                },
            },
        ),
    ]

    results: list[ProbeResult] = []
    async with httpx.AsyncClient(timeout=args.timeout_seconds) as client:
        for method, path, payload in probes:
            result = await _probe_one(
                client,
                method=method,
                base_url=base_url,
                path=path,
                headers=headers,
                payload=payload,
            )
            results.append(result)

    pools_result = results[0]
    exec_results = results[1:]
    auth_ok = pools_result.status_code == 200
    execution_routes_exist = all((r.status_code is not None and r.status_code != 404) for r in exec_results)
    execution_api_available = execution_routes_exist and all(r.status_code is not None and r.status_code < 500 for r in exec_results)

    report = {
        "ok": auth_ok and execution_api_available,
        "base_url": base_url,
        "api_key_env": args.api_key_env,
        "api_key_len": len(api_key),
        "chain": args.chain,
        "chain_id": args.chain_id,
        "auth_ok": auth_ok,
        "execution_routes_exist": execution_routes_exist,
        "execution_api_available": execution_api_available,
        "results": [asdict(r) for r in results],
    }
    print(json.dumps(report, indent=2))

    if not auth_ok:
        return 1
    if not execution_api_available:
        return 2
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Krystal Cloud API auth and execution-route availability.")
    parser.add_argument("--api-key-env", default="KRYSTAL_CLOUD_API_KEY")
    parser.add_argument("--base-url", default=os.getenv("KRYSTAL_CLOUD_API_BASE_URL", "https://cloud-api.krystal.app"))
    parser.add_argument("--chain", default="Base")
    parser.add_argument("--chain-id", type=int, default=8453)
    parser.add_argument("--timeout-seconds", type=float, default=8.0)
    return parser.parse_args()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    _load_env_file(root / ".env")
    args = _parse_args()
    try:
        import asyncio

        return asyncio.run(_run_probe(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
