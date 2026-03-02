from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import httpx

from ..execution.models import PositionState
from .position_baseline import (
    ENTRY_BASELINE_MALFORMED,
    ENTRY_BASELINE_MISSING,
    FileBackedPositionBaselineProvider,
    PositionEntryBaselineProvider,
)

RequestFn = Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]]
PriceRequestFn = Callable[[list[str], float], Awaitable[dict[str, Any]]]

ARBITRUM_CHAIN_NAME = "Arbitrum"
UNISWAP_V3_POSITION_MANAGER_ARBITRUM = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"
UNISWAP_V3_FACTORY_ARBITRUM = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
COINGECKO_TOKEN_PRICE_URL = (
    "https://api.coingecko.com/api/v3/simple/token_price/arbitrum-one"
)

# ABI selectors (keccak(function_signature)[:4])
_BALANCE_OF_SELECTOR = "0x70a08231"  # balanceOf(address)
_TOKEN_OF_OWNER_BY_INDEX_SELECTOR = "0x2f745c59"  # tokenOfOwnerByIndex(address,uint256)
_POSITIONS_SELECTOR = "0x99fbab88"  # positions(uint256)
_GET_POOL_SELECTOR = "0x1698ee82"  # getPool(address,address,uint24)
_SLOT0_SELECTOR = "0x3850c7bd"  # slot0()
_DECIMALS_SELECTOR = "0x313ce567"  # decimals()

logger = logging.getLogger(__name__)


class PositionReaderError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass
class _RawPosition:
    token_id: int
    token0: str
    token1: str
    fee: int
    tick_lower: int
    tick_upper: int
    liquidity: int
    tokens_owed_0: int
    tokens_owed_1: int


class ArbitrumUniswapV3PositionReader:
    """Direct-RPC reader for active Uniswap v3 NFT positions on Arbitrum."""

    def __init__(
        self,
        *,
        rpc_url: str,
        position_manager_address: str = UNISWAP_V3_POSITION_MANAGER_ARBITRUM,
        factory_address: str = UNISWAP_V3_FACTORY_ARBITRUM,
        timeout_seconds: float = 8.0,
        stale_after_seconds: int = 120,
        price_ttl_seconds: int = 60,
        request_fn: RequestFn | None = None,
        price_request_fn: PriceRequestFn | None = None,
        baseline_provider: PositionEntryBaselineProvider | None = None,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        rpc = (rpc_url or "").strip()
        if not rpc:
            raise ValueError("RPC_URL_MISSING")
        self.rpc_url = rpc
        self.position_manager_address = self._normalize_address(
            position_manager_address
        )
        self.factory_address = self._normalize_address(factory_address)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.stale_after_seconds = max(30, int(stale_after_seconds))
        self.price_ttl_seconds = max(10, int(price_ttl_seconds))
        self._request_fn = request_fn
        self._price_request_fn = price_request_fn
        self._baseline_provider = (
            baseline_provider or FileBackedPositionBaselineProvider()
        )
        self._now_fn = now_fn or time.time
        self._pool_cache: dict[tuple[str, str, int], str] = {}
        self._token_decimals_cache: dict[str, int] = {}
        self._token_price_cache: dict[str, tuple[float | None, int]] = {}

    async def load_active_position_states(
        self, wallet_address: str
    ) -> list[PositionState]:
        owner = self._normalize_address(wallet_address)
        if not owner:
            return []

        balance = await self._read_balance(owner)
        if balance <= 0:
            return []

        active_positions: list[tuple[_RawPosition, int | None, list[str]]] = []
        for idx in range(balance):
            token_id = await self._read_token_id(owner, idx)
            if token_id is None:
                continue

            raw = await self._read_position(token_id)
            if raw is None or raw.liquidity <= 0:
                continue

            current_tick, stale_reasons = await self._read_current_tick(raw)
            active_positions.append((raw, current_tick, stale_reasons))

        if not active_positions:
            return []

        await self._prefetch_token_prices([raw for raw, _, _ in active_positions])

        now_ts = int(self._now_fn())
        states: list[PositionState] = []
        for raw, current_tick, stale_reasons in active_positions:
            position_ref = f"uni-v3:{raw.token_id}"
            is_stale = len(stale_reasons) > 0
            freshness_at = (
                now_ts
                if not is_stale
                else max(0, now_ts - self.stale_after_seconds - 1)
            )
            unclaimed_fees_usd, fee_reason_codes = (
                await self._compute_unclaimed_fees_usd(raw)
            )
            valuation_tick = (
                current_tick if current_tick is not None else raw.tick_lower
            )
            position_value_usd, valuation_reason_codes, amount_token0, amount_token1 = (
                await self._compute_position_value_usd(
                    raw,
                    valuation_tick,
                )
            )
            pnl_hodl_metadata = self._build_pnl_hodl_metadata(
                position_ref=position_ref,
                token0=raw.token0,
                token1=raw.token1,
                position_value_usd=position_value_usd,
                unclaimed_fees_usd=unclaimed_fees_usd,
                valuation_reason_codes=valuation_reason_codes,
            )

            states.append(
                PositionState(
                    chain=ARBITRUM_CHAIN_NAME,
                    position_ref=position_ref,
                    current_tick=(
                        current_tick if current_tick is not None else raw.tick_lower
                    ),
                    lower_tick=raw.tick_lower,
                    upper_tick=raw.tick_upper,
                    liquidity=float(raw.liquidity),
                    unclaimed_fees_usd=unclaimed_fees_usd,
                    position_value_usd=position_value_usd,
                    position_manager=self.position_manager_address,
                    data_freshness_at=freshness_at,
                    stale=is_stale,
                    stale_reason_codes=stale_reasons,
                    metadata={
                        "token_id": raw.token_id,
                        "token0": raw.token0,
                        "token1": raw.token1,
                        "fee_tier": raw.fee,
                        "tokens_owed_0": str(raw.tokens_owed_0),
                        "tokens_owed_1": str(raw.tokens_owed_1),
                        "fee_reason_codes": fee_reason_codes,
                        "valuation_reason_codes": valuation_reason_codes,
                        "position_amount_token0": f"{amount_token0:.18f}",
                        "position_amount_token1": f"{amount_token1:.18f}",
                        "position_value_source": "LIQUIDITY_TICK_MODEL_V1",
                        **pnl_hodl_metadata,
                    },
                )
            )

        return states

    def _build_pnl_hodl_metadata(
        self,
        *,
        position_ref: str,
        token0: str,
        token1: str,
        position_value_usd: float,
        unclaimed_fees_usd: float,
        valuation_reason_codes: list[str],
    ) -> dict[str, Any]:
        lookup = self._baseline_provider.lookup(position_ref)
        baseline = lookup.baseline
        if baseline is None:
            reason = str(lookup.reason_code or ENTRY_BASELINE_MISSING)
            return {
                "pnl_reason_codes": [reason],
                "hodl_reason_codes": [reason],
            }

        if len(valuation_reason_codes) > 0:
            reason_codes = sorted(
                set([*valuation_reason_codes, "POSITION_VALUE_UNAVAILABLE"])
            )
            return {
                "pnl_reason_codes": reason_codes,
                "hodl_reason_codes": reason_codes,
            }

        current_price_0 = self._get_cached_price_usd(token0)
        current_price_1 = self._get_cached_price_usd(token1)
        if current_price_0 is None or current_price_1 is None:
            return {
                "pnl_reason_codes": ["STALE_PRICE"],
                "hodl_reason_codes": ["STALE_PRICE"],
            }

        entry_value_usd = baseline.entry_value_usd
        hodl_value_usd = (baseline.entry_token0_amount * current_price_0) + (
            baseline.entry_token1_amount * current_price_1
        )
        net_pnl_usd = (position_value_usd + unclaimed_fees_usd) - entry_value_usd
        pnl_vs_hodl_usd = (position_value_usd + unclaimed_fees_usd) - hodl_value_usd

        values = [entry_value_usd, hodl_value_usd, net_pnl_usd, pnl_vs_hodl_usd]
        if any((not math.isfinite(v) for v in values)):
            return {
                "pnl_reason_codes": [ENTRY_BASELINE_MALFORMED],
                "hodl_reason_codes": [ENTRY_BASELINE_MALFORMED],
            }

        return {
            "entry_value_usd": entry_value_usd,
            "hodl_value_usd": hodl_value_usd,
            "net_pnl_usd": net_pnl_usd,
            "pnl_vs_hodl_usd": pnl_vs_hodl_usd,
            "pnl_reason_codes": [],
            "hodl_reason_codes": [],
        }

    async def _read_balance(self, owner: str) -> int:
        data = self._BALANCE_OF(owner)
        result = await self._eth_call(self.position_manager_address, data)
        if not isinstance(result, str) or not result.startswith("0x"):
            raise PositionReaderError("BALANCE_OF_INVALID")
        return self._decode_uint(result)

    async def _read_token_id(self, owner: str, index: int) -> int | None:
        data = self._TOKEN_OF_OWNER_BY_INDEX(owner, index)
        result = await self._eth_call(self.position_manager_address, data)
        if not isinstance(result, str) or not result.startswith("0x"):
            return None
        return self._decode_uint(result)

    async def _read_position(self, token_id: int) -> _RawPosition | None:
        data = self._POSITIONS(token_id)
        result = await self._eth_call(self.position_manager_address, data)
        words = self._split_words(result, expected_min_words=12)
        if words is None:
            return None

        token0 = self._decode_address_word(words[2])
        token1 = self._decode_address_word(words[3])
        if not token0 or not token1:
            return None

        return _RawPosition(
            token_id=token_id,
            token0=token0,
            token1=token1,
            fee=self._decode_uint_word(words[4]),
            tick_lower=self._decode_int_word(words[5]),
            tick_upper=self._decode_int_word(words[6]),
            liquidity=self._decode_uint_word(words[7]),
            tokens_owed_0=self._decode_uint_word(words[10]),
            tokens_owed_1=self._decode_uint_word(words[11]),
        )

    async def _read_current_tick(
        self, position: _RawPosition
    ) -> tuple[int | None, list[str]]:
        pool_address = await self._get_pool(
            position.token0, position.token1, position.fee
        )
        if not pool_address:
            return None, ["STALE_POSITION_DATA"]

        result = await self._eth_call(pool_address, _SLOT0_SELECTOR)
        words = self._split_words(result, expected_min_words=2)
        if words is None:
            return None, ["STALE_POSITION_DATA"]

        return self._decode_int_word(words[1]), []

    async def _get_pool(self, token0: str, token1: str, fee: int) -> str:
        key = (token0.lower(), token1.lower(), int(fee))
        cached = self._pool_cache.get(key, "")
        if cached:
            return cached

        data = self._GET_POOL(token0, token1, fee)
        result = await self._eth_call(self.factory_address, data)
        words = self._split_words(result, expected_min_words=1)
        if words is None:
            return ""
        pool = self._decode_address_word(words[0]) or ""
        if pool:
            self._pool_cache[key] = pool
        return pool

    async def _compute_unclaimed_fees_usd(
        self, raw: _RawPosition
    ) -> tuple[float, list[str]]:
        reason_codes: list[str] = []
        decimals_0 = await self._get_token_decimals(raw.token0)
        decimals_1 = await self._get_token_decimals(raw.token1)
        if decimals_0 is None or decimals_1 is None:
            reason_codes.append("TOKEN_DECIMALS_MISSING")
            return 0.0, reason_codes

        price_0 = self._get_cached_price_usd(raw.token0)
        price_1 = self._get_cached_price_usd(raw.token1)
        if price_0 is None or price_1 is None:
            reason_codes.append("STALE_PRICE")
            return 0.0, reason_codes

        amount_0 = float(raw.tokens_owed_0) / float(10**decimals_0)
        amount_1 = float(raw.tokens_owed_1) / float(10**decimals_1)
        return (amount_0 * price_0) + (amount_1 * price_1), reason_codes

    async def _compute_position_value_usd(
        self,
        raw: _RawPosition,
        current_tick: int,
    ) -> tuple[float, list[str], float, float]:
        reason_codes: list[str] = []
        decimals_0 = await self._get_token_decimals(raw.token0)
        decimals_1 = await self._get_token_decimals(raw.token1)
        if decimals_0 is None or decimals_1 is None:
            reason_codes.append("TOKEN_DECIMALS_MISSING")
            return 0.0, reason_codes, 0.0, 0.0

        amount_raw_0, amount_raw_1 = self._compute_raw_position_amounts(
            liquidity=raw.liquidity,
            current_tick=current_tick,
            tick_lower=raw.tick_lower,
            tick_upper=raw.tick_upper,
        )
        if amount_raw_0 < 0.0 or amount_raw_1 < 0.0:
            reason_codes.append("POSITION_MATH_INVALID")
            return 0.0, reason_codes, 0.0, 0.0

        price_0 = self._get_cached_price_usd(raw.token0)
        price_1 = self._get_cached_price_usd(raw.token1)
        if price_0 is None or price_1 is None:
            reason_codes.append("STALE_PRICE")
            return 0.0, reason_codes, 0.0, 0.0

        amount_0 = amount_raw_0 / float(10**decimals_0)
        amount_1 = amount_raw_1 / float(10**decimals_1)
        position_value_usd = (amount_0 * price_0) + (amount_1 * price_1)
        return max(0.0, position_value_usd), reason_codes, amount_0, amount_1

    @staticmethod
    def _compute_raw_position_amounts(
        *,
        liquidity: int,
        current_tick: int,
        tick_lower: int,
        tick_upper: int,
    ) -> tuple[float, float]:
        if liquidity <= 0 or tick_lower >= tick_upper:
            return 0.0, 0.0

        sqrt_lower = math.pow(1.0001, tick_lower / 2.0)
        sqrt_upper = math.pow(1.0001, tick_upper / 2.0)
        if sqrt_lower <= 0.0 or sqrt_upper <= 0.0 or sqrt_upper <= sqrt_lower:
            return 0.0, 0.0

        amount0_raw = 0.0
        amount1_raw = 0.0
        liq = float(liquidity)

        if current_tick <= tick_lower:
            amount0_raw = liq * ((sqrt_upper - sqrt_lower) / (sqrt_lower * sqrt_upper))
        elif current_tick >= tick_upper:
            amount1_raw = liq * (sqrt_upper - sqrt_lower)
        else:
            sqrt_current = math.pow(1.0001, current_tick / 2.0)
            if sqrt_current <= 0.0:
                return 0.0, 0.0
            amount0_raw = liq * (
                (sqrt_upper - sqrt_current) / (sqrt_current * sqrt_upper)
            )
            amount1_raw = liq * (sqrt_current - sqrt_lower)

        return max(0.0, amount0_raw), max(0.0, amount1_raw)

    async def _prefetch_token_prices(self, positions: list[_RawPosition]) -> None:
        unique_tokens = {raw.token0.lower() for raw in positions}
        unique_tokens.update(raw.token1.lower() for raw in positions)
        if not unique_tokens:
            return

        now_ts = int(self._now_fn())
        to_fetch = [
            token for token in unique_tokens if self._should_fetch_price(token, now_ts)
        ]
        if not to_fetch:
            return

        try:
            payload = await self._fetch_token_prices_usd(sorted(to_fetch))
        except Exception as exc:  # noqa: BLE001
            for token in to_fetch:
                self._token_price_cache[token] = (None, now_ts)
            logger.warning(
                "Position reader price fallback: reason=STALE_PRICE err=%s",
                exc.__class__.__name__,
            )
            return

        for token in to_fetch:
            entry = payload.get(token) if isinstance(payload, dict) else None
            usd = entry.get("usd") if isinstance(entry, dict) else None
            if usd is None:
                self._token_price_cache[token] = (None, now_ts)
                continue
            try:
                self._token_price_cache[token] = (float(usd), now_ts)
            except (TypeError, ValueError):
                self._token_price_cache[token] = (None, now_ts)

    async def _fetch_token_prices_usd(self, tokens: list[str]) -> dict[str, Any]:
        if self._price_request_fn is not None:
            payload = await self._price_request_fn(tokens, self.timeout_seconds)
            if isinstance(payload, dict):
                return {str(k).lower(): v for k, v in payload.items()}
            raise PositionReaderError("PRICE_API_INVALID_RESPONSE")

        # CoinGecko free tier allows 1 contract address per request — query one at a time.
        merged: dict[str, Any] = {}
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds, http2=False
        ) as client:
            for token in tokens:
                try:
                    params = {"contract_addresses": token, "vs_currencies": "usd"}
                    resp = await client.get(COINGECKO_TOKEN_PRICE_URL, params=params)
                    resp.raise_for_status()
                    body = resp.json()
                    if isinstance(body, dict):
                        for k, v in body.items():
                            merged[str(k).lower()] = v
                except (httpx.TimeoutException, httpx.HTTPError, ValueError):
                    pass  # individual token failure → leave out of merged, will be STALE_PRICE
        return merged

    async def _get_token_decimals(self, token_address: str) -> int | None:
        token = self._normalize_address(token_address)
        if not token:
            return None
        cached = self._token_decimals_cache.get(token)
        if cached is not None:
            return cached

        try:
            result = await self._eth_call(token, _DECIMALS_SELECTOR)
        except Exception:  # noqa: BLE001
            return None
        words = self._split_words(result, expected_min_words=1)
        if words is None:
            return None
        decimals = self._decode_uint_word(words[0])
        if decimals < 0 or decimals > 255:
            return None
        self._token_decimals_cache[token] = decimals
        return decimals

    def _get_cached_price_usd(self, token_address: str) -> float | None:
        token = self._normalize_address(token_address)
        if not token:
            return None
        cached = self._token_price_cache.get(token)
        if not cached:
            return None
        value, _ = cached
        return value

    def _should_fetch_price(self, token_address: str, now_ts: int) -> bool:
        token = self._normalize_address(token_address)
        if not token:
            return False
        cached = self._token_price_cache.get(token)
        if not cached:
            return True
        _, ts = cached
        return (now_ts - int(ts)) > self.price_ttl_seconds

    async def _eth_call(self, to_address: str, data_hex: str) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to_address, "data": data_hex}, "latest"],
        }
        body = await self._post_json(payload)
        error = body.get("error")
        if isinstance(error, dict):
            raise PositionReaderError("RPC_ETH_CALL_ERROR")
        result = body.get("result")
        if not isinstance(result, str):
            raise PositionReaderError("RPC_ETH_CALL_RESULT_MISSING")
        return result

    async def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._request_fn is not None:
            response = await self._request_fn(
                self.rpc_url, payload, self.timeout_seconds
            )
            if isinstance(response, dict):
                return response
            raise PositionReaderError("RPC_INVALID_RESPONSE")
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds, http2=False
            ) as client:
                resp = await client.post(self.rpc_url, json=payload)
                resp.raise_for_status()
                body = resp.json()
            if not isinstance(body, dict):
                raise PositionReaderError("RPC_INVALID_JSON")
            return body
        except httpx.TimeoutException as exc:
            raise PositionReaderError("RPC_TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise PositionReaderError("RPC_HTTP_ERROR") from exc
        except ValueError as exc:
            raise PositionReaderError("RPC_INVALID_JSON") from exc

    @staticmethod
    def _normalize_address(value: str) -> str:
        text = str(value or "").strip().lower()
        if not text.startswith("0x") or len(text) != 42:
            return ""
        return text

    @staticmethod
    def _split_words(result_hex: str, *, expected_min_words: int) -> list[str] | None:
        if not isinstance(result_hex, str):
            return None
        raw = result_hex[2:] if result_hex.startswith("0x") else result_hex
        if len(raw) < expected_min_words * 64 or len(raw) % 64 != 0:
            return None
        return [raw[i : i + 64] for i in range(0, len(raw), 64)]

    @staticmethod
    def _decode_uint(result_hex: str) -> int:
        raw = result_hex[2:] if result_hex.startswith("0x") else result_hex
        return int(raw or "0", 16)

    @staticmethod
    def _decode_uint_word(word_hex: str) -> int:
        return int(word_hex or "0", 16)

    @staticmethod
    def _decode_int_word(word_hex: str) -> int:
        value = int(word_hex or "0", 16)
        if value >= (1 << 255):
            value -= 1 << 256
        return value

    @staticmethod
    def _decode_address_word(word_hex: str) -> str | None:
        raw = (word_hex or "").lower()
        if len(raw) != 64:
            return None
        addr = raw[-40:]
        if set(addr) == {"0"}:
            return None
        return f"0x{addr}"

    @staticmethod
    def _encode_uint_word(value: int) -> str:
        return f"{int(value):064x}"

    @classmethod
    def _encode_address_word(cls, address: str) -> str:
        normalized = cls._normalize_address(address)
        if not normalized:
            raise ValueError("ADDRESS_INVALID")
        return ("0" * 24) + normalized[2:]

    @classmethod
    def _BALANCE_OF(cls, owner: str) -> str:
        return _BALANCE_OF_SELECTOR + cls._encode_address_word(owner)

    @classmethod
    def _TOKEN_OF_OWNER_BY_INDEX(cls, owner: str, index: int) -> str:
        return (
            _TOKEN_OF_OWNER_BY_INDEX_SELECTOR
            + cls._encode_address_word(owner)
            + cls._encode_uint_word(index)
        )

    @classmethod
    def _POSITIONS(cls, token_id: int) -> str:
        return _POSITIONS_SELECTOR + cls._encode_uint_word(token_id)

    @classmethod
    def _GET_POOL(cls, token0: str, token1: str, fee: int) -> str:
        return (
            _GET_POOL_SELECTOR
            + cls._encode_address_word(token0)
            + cls._encode_address_word(token1)
            + cls._encode_uint_word(fee)
        )
