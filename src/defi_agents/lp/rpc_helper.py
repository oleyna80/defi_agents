"""Minimal RPC helper for fetching Uniswap V3 slot0 tick via raw eth_call.

No web3.py dependency — uses httpx + raw JSON-RPC.
Fail-safe: any error → returns None (scanner runs with rpc_tick=None → UNVERIFIED).
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

# slot0() selector: keccak256("slot0()")[:4] = 0x3850c7bd
_SLOT0_SELECTOR = "0x3850c7bd"

# Chain name → env var name for RPC URL
CHAIN_RPC_ENV_MAP: dict[str, str] = {
    "Ethereum": "RPC_URL_ETHEREUM",
    "Arbitrum": "RPC_URL_ARBITRUM",
    "Base": "RPC_URL_BASE",
}


async def fetch_slot0_tick(
    rpc_url: str,
    pool_address: str,
    *,
    timeout_seconds: float = 3.0,
) -> int | None:
    """Fetch current tick from a Uniswap V3 pool's slot0() via raw eth_call.

    Returns the current tick (int) or None on any failure.
    slot0() returns: (sqrtPriceX96, tick, observationIndex, observationCardinality,
                      observationCardinalityNext, feeProtocol, unlocked)
    tick is the second word (bytes 32..64) in the return data, as int24 (signed).
    """
    addr = (pool_address or "").strip().lower()
    if not addr.startswith("0x") or len(addr) != 42:
        return None

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [
            {"to": addr, "data": _SLOT0_SELECTOR},
            "latest",
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(rpc_url, json=payload)
        if not response.is_success:
            logger.warning("slot0 RPC HTTP error: status=%s", response.status_code)
            return None

        body = response.json()
        result = body.get("result")
        if not isinstance(result, str) or len(result) < 130:  # 0x + 64 hex chars minimum
            logger.warning("slot0 RPC invalid result length")
            return None

        # tick is the second 32-byte word (offset 2+64 to 2+128)
        tick_hex = result[66:130]
        tick_raw = int(tick_hex, 16)

        # Handle int24 sign extension (tick can be negative)
        if tick_raw >= (1 << 255):
            tick_raw -= 1 << 256

        return tick_raw

    except httpx.TimeoutException:
        logger.warning("slot0 RPC timeout for pool=%s", addr[:10])
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("slot0 RPC error: %s", exc.__class__.__name__)
        return None
