import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from defi_agents.tracker.position_reader import (  # noqa: E402
    ArbitrumUniswapV3PositionReader,
    BaseUniswapV3ChainPositionReader,
    HypeEVMUniswapV3PositionReader,
    OptimismUniswapV3PositionReader,
    UNISWAP_V3_FACTORY_BASE,
    UNISWAP_V3_FACTORY_ARBITRUM,
    UNISWAP_V3_FACTORY_HYPEEVM,
    UNISWAP_V3_FACTORY_OPTIMISM,
    UNISWAP_V3_POSITION_MANAGER_BASE,
    UNISWAP_V3_POSITION_MANAGER_HYPEEVM,
    UNISWAP_V3_POSITION_MANAGER_OPTIMISM,
    UNISWAP_V3_POSITION_MANAGER_ARBITRUM,
)
from defi_agents.tracker.position_baseline import (  # noqa: E402
    BaselineLookupResult,
    ENTRY_BASELINE_INCOMPLETE,
    ENTRY_BASELINE_MALFORMED,
    ENTRY_BASELINE_MISSING,
    PositionEntryBaseline,
)


def _run(coro):
    return asyncio.run(coro)


class _StaticBaselineProvider:
    def __init__(
        self, lookup_by_ref=None, default_reason: str = ENTRY_BASELINE_MISSING
    ):
        self._lookup_by_ref = {
            str(k).lower(): v for k, v in dict(lookup_by_ref or {}).items()
        }
        self._default_reason = default_reason

    def lookup(
        self, position_ref: str, chain_name: str | None = None
    ) -> BaselineLookupResult:
        ref = str(position_ref).lower()
        chain = str(chain_name or "").strip().lower()
        if chain:
            chain_ref = f"{chain}:{ref}"
            hit = self._lookup_by_ref.get(chain_ref)
            if hit is not None:
                return hit

        return self._lookup_by_ref.get(ref, BaselineLookupResult(reason_code=self._default_reason))


def _uint_word(value: int) -> str:
    return f"{int(value):064x}"


def _int_word(value: int) -> str:
    if value < 0:
        value = (1 << 256) + value
    return f"{int(value):064x}"


def _address_word(address: str) -> str:
    return ("0" * 24) + address.lower().replace("0x", "")


def _words_hex(*words: str) -> str:
    return "0x" + "".join(words)


def test_position_reader_loads_only_active_positions():
    owner = "0x1111111111111111111111111111111111111111"
    token0 = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    token1 = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    pool = "0x2222222222222222222222222222222222222222"
    pm = UNISWAP_V3_POSITION_MANAGER_ARBITRUM.lower()
    factory = UNISWAP_V3_FACTORY_ARBITRUM.lower()

    p1 = _words_hex(
        _uint_word(0),
        _address_word("0x0000000000000000000000000000000000000000"),
        _address_word(token0),
        _address_word(token1),
        _uint_word(3000),
        _int_word(-100),
        _int_word(100),
        _uint_word(0),  # inactive
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
    )
    p2 = _words_hex(
        _uint_word(0),
        _address_word("0x0000000000000000000000000000000000000000"),
        _address_word(token0),
        _address_word(token1),
        _uint_word(3000),
        _int_word(-120),
        _int_word(120),
        _uint_word(500_000),  # active
        _uint_word(0),
        _uint_word(0),
        _uint_word(10),
        _uint_word(20),
    )
    slot0 = _words_hex(
        _uint_word(0),
        _int_word(77),  # current tick
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(1),
    )

    mapping = {
        (pm, ArbitrumUniswapV3PositionReader._BALANCE_OF(owner).lower()): _words_hex(
            _uint_word(2)
        ),
        (
            pm,
            ArbitrumUniswapV3PositionReader._TOKEN_OF_OWNER_BY_INDEX(owner, 0).lower(),
        ): _words_hex(_uint_word(1)),
        (
            pm,
            ArbitrumUniswapV3PositionReader._TOKEN_OF_OWNER_BY_INDEX(owner, 1).lower(),
        ): _words_hex(_uint_word(2)),
        (pm, ArbitrumUniswapV3PositionReader._POSITIONS(1).lower()): p1,
        (pm, ArbitrumUniswapV3PositionReader._POSITIONS(2).lower()): p2,
        (
            factory,
            ArbitrumUniswapV3PositionReader._GET_POOL(token0, token1, 3000).lower(),
        ): _words_hex(_address_word(pool)),
        (pool, "0x3850c7bd"): slot0,
        (token0.lower(), "0x313ce567"): _words_hex(_uint_word(6)),
        (token1.lower(), "0x313ce567"): _words_hex(_uint_word(18)),
    }

    async def request_fn(_rpc_url, payload, _timeout):
        params = payload["params"][0]
        key = (str(params["to"]).lower(), str(params["data"]).lower())
        return {"jsonrpc": "2.0", "id": 1, "result": mapping[key]}

    async def price_request_fn(tokens, _timeout):
        return {
            str(token).lower(): {
                "usd": 1.0 if str(token).lower() == token0.lower() else 3000.0
            }
            for token in tokens
        }

    reader = ArbitrumUniswapV3PositionReader(
        rpc_url="https://rpc.local",
        request_fn=request_fn,
        price_request_fn=price_request_fn,
        baseline_provider=_StaticBaselineProvider(
            {
                "arbitrum:uni-v3:2": BaselineLookupResult(
                    baseline=PositionEntryBaseline(
                        position_ref="arbitrum:uni-v3:2",
                        entry_token0_amount=0.25,
                        entry_token1_amount=0.01,
                        entry_price_token0_usd=1.0,
                        entry_price_token1_usd=2500.0,
                    )
                )
            }
        ),
        now_fn=lambda: 1700000000.0,
    )
    states = _run(reader.load_active_position_states(owner))
    assert len(states) == 1
    state = states[0]
    assert state.chain == "Arbitrum"
    assert state.position_ref == "uni-v3:2"
    assert state.lower_tick == -120
    assert state.upper_tick == 120
    assert state.current_tick == 77
    assert state.liquidity == 500000.0
    assert state.stale is False
    assert state.data_freshness_at == 1700000000
    assert state.unclaimed_fees_usd == (10.0 / 1e6) + (20.0 / 1e18 * 3000.0)
    assert state.metadata.get("fee_reason_codes") == []
    assert state.position_value_usd > 0.0
    assert state.metadata.get("valuation_reason_codes") == []
    assert state.metadata.get("position_value_source") == "LIQUIDITY_TICK_MODEL_V1"
    assert state.metadata.get("pnl_reason_codes") == []
    assert state.metadata.get("hodl_reason_codes") == []
    assert state.metadata.get("entry_value_usd") == 25.25
    assert state.metadata.get("hodl_value_usd") == 30.25
    expected_net_pnl = state.position_value_usd + state.unclaimed_fees_usd - 25.25
    expected_vs_hodl = state.position_value_usd + state.unclaimed_fees_usd - 30.25
    assert abs(float(state.metadata.get("net_pnl_usd")) - expected_net_pnl) < 1e-9
    assert abs(float(state.metadata.get("pnl_vs_hodl_usd")) - expected_vs_hodl) < 1e-9


def test_position_reader_baseline_missing_sets_explicit_reason_code():
    owner = "0x1111111111111111111111111111111111111111"
    token0 = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    token1 = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    pool = "0x2525252525252525252525252525252525252525"
    pm = UNISWAP_V3_POSITION_MANAGER_ARBITRUM.lower()
    factory = UNISWAP_V3_FACTORY_ARBITRUM.lower()

    position = _words_hex(
        _uint_word(0),
        _address_word("0x0000000000000000000000000000000000000000"),
        _address_word(token0),
        _address_word(token1),
        _uint_word(3000),
        _int_word(-120),
        _int_word(120),
        _uint_word(500_000),
        _uint_word(0),
        _uint_word(0),
        _uint_word(10),
        _uint_word(20),
    )
    slot0 = _words_hex(
        _uint_word(0),
        _int_word(77),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(1),
    )
    mapping = {
        (pm, ArbitrumUniswapV3PositionReader._BALANCE_OF(owner).lower()): _words_hex(
            _uint_word(1)
        ),
        (
            pm,
            ArbitrumUniswapV3PositionReader._TOKEN_OF_OWNER_BY_INDEX(owner, 0).lower(),
        ): _words_hex(_uint_word(2)),
        (pm, ArbitrumUniswapV3PositionReader._POSITIONS(2).lower()): position,
        (
            factory,
            ArbitrumUniswapV3PositionReader._GET_POOL(token0, token1, 3000).lower(),
        ): _words_hex(_address_word(pool)),
        (pool, "0x3850c7bd"): slot0,
        (token0.lower(), "0x313ce567"): _words_hex(_uint_word(6)),
        (token1.lower(), "0x313ce567"): _words_hex(_uint_word(18)),
    }

    async def request_fn(_rpc_url, payload, _timeout):
        params = payload["params"][0]
        key = (str(params["to"]).lower(), str(params["data"]).lower())
        return {"jsonrpc": "2.0", "id": 1, "result": mapping[key]}

    async def price_request_fn(tokens, _timeout):
        return {
            str(token).lower(): {
                "usd": 1.0 if str(token).lower() == token0.lower() else 3000.0
            }
            for token in tokens
        }

    reader = ArbitrumUniswapV3PositionReader(
        rpc_url="https://rpc.local",
        request_fn=request_fn,
        price_request_fn=price_request_fn,
        baseline_provider=_StaticBaselineProvider(),
        now_fn=lambda: 1700000000.0,
    )
    states = _run(reader.load_active_position_states(owner))
    assert len(states) == 1
    metadata = states[0].metadata
    assert metadata.get("pnl_reason_codes") == [ENTRY_BASELINE_MISSING]
    assert metadata.get("hodl_reason_codes") == [ENTRY_BASELINE_MISSING]
    assert "entry_value_usd" not in metadata
    assert "hodl_value_usd" not in metadata
    assert "net_pnl_usd" not in metadata
    assert "pnl_vs_hodl_usd" not in metadata


def test_position_reader_baseline_incomplete_sets_explicit_reason_code():
    owner = "0x1111111111111111111111111111111111111111"
    token0 = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    token1 = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    pool = "0x2626262626262626262626262626262626262626"
    pm = UNISWAP_V3_POSITION_MANAGER_ARBITRUM.lower()
    factory = UNISWAP_V3_FACTORY_ARBITRUM.lower()

    position = _words_hex(
        _uint_word(0),
        _address_word("0x0000000000000000000000000000000000000000"),
        _address_word(token0),
        _address_word(token1),
        _uint_word(3000),
        _int_word(-120),
        _int_word(120),
        _uint_word(500_000),
        _uint_word(0),
        _uint_word(0),
        _uint_word(10),
        _uint_word(20),
    )
    slot0 = _words_hex(
        _uint_word(0),
        _int_word(77),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(1),
    )
    mapping = {
        (pm, ArbitrumUniswapV3PositionReader._BALANCE_OF(owner).lower()): _words_hex(
            _uint_word(1)
        ),
        (
            pm,
            ArbitrumUniswapV3PositionReader._TOKEN_OF_OWNER_BY_INDEX(owner, 0).lower(),
        ): _words_hex(_uint_word(2)),
        (pm, ArbitrumUniswapV3PositionReader._POSITIONS(2).lower()): position,
        (
            factory,
            ArbitrumUniswapV3PositionReader._GET_POOL(token0, token1, 3000).lower(),
        ): _words_hex(_address_word(pool)),
        (pool, "0x3850c7bd"): slot0,
        (token0.lower(), "0x313ce567"): _words_hex(_uint_word(6)),
        (token1.lower(), "0x313ce567"): _words_hex(_uint_word(18)),
    }

    async def request_fn(_rpc_url, payload, _timeout):
        params = payload["params"][0]
        key = (str(params["to"]).lower(), str(params["data"]).lower())
        return {"jsonrpc": "2.0", "id": 1, "result": mapping[key]}

    async def price_request_fn(tokens, _timeout):
        return {
            str(token).lower(): {
                "usd": 1.0 if str(token).lower() == token0.lower() else 3000.0
            }
            for token in tokens
        }

    reader = ArbitrumUniswapV3PositionReader(
        rpc_url="https://rpc.local",
        request_fn=request_fn,
        price_request_fn=price_request_fn,
        baseline_provider=_StaticBaselineProvider(
            {
                "uni-v3:2": BaselineLookupResult(reason_code=ENTRY_BASELINE_INCOMPLETE),
            }
        ),
        now_fn=lambda: 1700000000.0,
    )
    states = _run(reader.load_active_position_states(owner))
    assert len(states) == 1
    metadata = states[0].metadata
    assert metadata.get("pnl_reason_codes") == [ENTRY_BASELINE_INCOMPLETE]
    assert metadata.get("hodl_reason_codes") == [ENTRY_BASELINE_INCOMPLETE]
    assert "entry_value_usd" not in metadata
    assert "hodl_value_usd" not in metadata
    assert "net_pnl_usd" not in metadata
    assert "pnl_vs_hodl_usd" not in metadata


def test_position_reader_baseline_malformed_sets_explicit_reason_code():
    owner = "0x1111111111111111111111111111111111111111"
    token0 = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    token1 = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    pool = "0x2727272727272727272727272727272727272727"
    pm = UNISWAP_V3_POSITION_MANAGER_ARBITRUM.lower()
    factory = UNISWAP_V3_FACTORY_ARBITRUM.lower()

    position = _words_hex(
        _uint_word(0),
        _address_word("0x0000000000000000000000000000000000000000"),
        _address_word(token0),
        _address_word(token1),
        _uint_word(3000),
        _int_word(-120),
        _int_word(120),
        _uint_word(500_000),
        _uint_word(0),
        _uint_word(0),
        _uint_word(10),
        _uint_word(20),
    )
    slot0 = _words_hex(
        _uint_word(0),
        _int_word(77),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(1),
    )
    mapping = {
        (pm, ArbitrumUniswapV3PositionReader._BALANCE_OF(owner).lower()): _words_hex(
            _uint_word(1)
        ),
        (
            pm,
            ArbitrumUniswapV3PositionReader._TOKEN_OF_OWNER_BY_INDEX(owner, 0).lower(),
        ): _words_hex(_uint_word(2)),
        (pm, ArbitrumUniswapV3PositionReader._POSITIONS(2).lower()): position,
        (
            factory,
            ArbitrumUniswapV3PositionReader._GET_POOL(token0, token1, 3000).lower(),
        ): _words_hex(_address_word(pool)),
        (pool, "0x3850c7bd"): slot0,
        (token0.lower(), "0x313ce567"): _words_hex(_uint_word(6)),
        (token1.lower(), "0x313ce567"): _words_hex(_uint_word(18)),
    }

    async def request_fn(_rpc_url, payload, _timeout):
        params = payload["params"][0]
        key = (str(params["to"]).lower(), str(params["data"]).lower())
        return {"jsonrpc": "2.0", "id": 1, "result": mapping[key]}

    async def price_request_fn(tokens, _timeout):
        return {
            str(token).lower(): {
                "usd": 1.0 if str(token).lower() == token0.lower() else 3000.0
            }
            for token in tokens
        }

    reader = ArbitrumUniswapV3PositionReader(
        rpc_url="https://rpc.local",
        request_fn=request_fn,
        price_request_fn=price_request_fn,
        baseline_provider=_StaticBaselineProvider(
            {
                "uni-v3:2": BaselineLookupResult(reason_code=ENTRY_BASELINE_MALFORMED),
            }
        ),
        now_fn=lambda: 1700000000.0,
    )
    states = _run(reader.load_active_position_states(owner))
    assert len(states) == 1
    metadata = states[0].metadata
    assert metadata.get("pnl_reason_codes") == [ENTRY_BASELINE_MALFORMED]
    assert metadata.get("hodl_reason_codes") == [ENTRY_BASELINE_MALFORMED]
    assert "entry_value_usd" not in metadata
    assert "hodl_value_usd" not in metadata
    assert "net_pnl_usd" not in metadata
    assert "pnl_vs_hodl_usd" not in metadata


def test_position_reader_marks_state_stale_when_slot0_unavailable():
    owner = "0x1111111111111111111111111111111111111111"
    token0 = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    token1 = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    pool = "0x3333333333333333333333333333333333333333"
    pm = UNISWAP_V3_POSITION_MANAGER_ARBITRUM.lower()
    factory = UNISWAP_V3_FACTORY_ARBITRUM.lower()

    position = _words_hex(
        _uint_word(0),
        _address_word("0x0000000000000000000000000000000000000000"),
        _address_word(token0),
        _address_word(token1),
        _uint_word(3000),
        _int_word(-60),
        _int_word(60),
        _uint_word(1_000),
        _uint_word(0),
        _uint_word(0),
        _uint_word(1),
        _uint_word(2),
    )

    mapping = {
        (pm, ArbitrumUniswapV3PositionReader._BALANCE_OF(owner).lower()): _words_hex(
            _uint_word(1)
        ),
        (
            pm,
            ArbitrumUniswapV3PositionReader._TOKEN_OF_OWNER_BY_INDEX(owner, 0).lower(),
        ): _words_hex(_uint_word(99)),
        (pm, ArbitrumUniswapV3PositionReader._POSITIONS(99).lower()): position,
        (
            factory,
            ArbitrumUniswapV3PositionReader._GET_POOL(token0, token1, 3000).lower(),
        ): _words_hex(_address_word(pool)),
        (pool, "0x3850c7bd"): "0x12",  # invalid slot0 payload
        (token0.lower(), "0x313ce567"): _words_hex(_uint_word(6)),
        (token1.lower(), "0x313ce567"): _words_hex(_uint_word(18)),
    }

    async def request_fn(_rpc_url, payload, _timeout):
        params = payload["params"][0]
        key = (str(params["to"]).lower(), str(params["data"]).lower())
        return {"jsonrpc": "2.0", "id": 1, "result": mapping[key]}

    async def price_request_fn(tokens, _timeout):
        return {str(token).lower(): {"usd": 2.0} for token in tokens}

    reader = ArbitrumUniswapV3PositionReader(
        rpc_url="https://rpc.local",
        request_fn=request_fn,
        price_request_fn=price_request_fn,
        baseline_provider=_StaticBaselineProvider(),
        now_fn=lambda: 1700000000.0,
        stale_after_seconds=120,
    )
    states = _run(reader.load_active_position_states(owner))
    assert len(states) == 1
    state = states[0]
    assert state.stale is True
    assert state.stale_reason_codes == ["STALE_POSITION_DATA"]
    assert state.current_tick == state.lower_tick  # fallback path
    assert state.data_freshness_at == 1699999879
    assert state.unclaimed_fees_usd > 0.0
    assert state.metadata.get("fee_reason_codes") == []
    assert state.position_value_usd > 0.0


def test_position_reader_returns_empty_for_invalid_wallet():
    reader = ArbitrumUniswapV3PositionReader(
        rpc_url="https://rpc.local",
        request_fn=None,
        baseline_provider=_StaticBaselineProvider(),
    )
    states = _run(reader.load_active_position_states("not-an-address"))
    assert states == []


def test_position_reader_sets_fee_zero_when_price_feed_is_unavailable():
    owner = "0x1111111111111111111111111111111111111111"
    token0 = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    token1 = "0x82af49447d8a07e3bd95bd0d56f35241523fbab1"
    pool = "0x4444444444444444444444444444444444444444"
    pm = UNISWAP_V3_POSITION_MANAGER_ARBITRUM.lower()
    factory = UNISWAP_V3_FACTORY_ARBITRUM.lower()
    position = _words_hex(
        _uint_word(0),
        _address_word("0x0000000000000000000000000000000000000000"),
        _address_word(token0),
        _address_word(token1),
        _uint_word(3000),
        _int_word(-50),
        _int_word(50),
        _uint_word(1_000),
        _uint_word(0),
        _uint_word(0),
        _uint_word(50_000_000),
        _uint_word(2_000_000_000_000_000),
    )
    slot0 = _words_hex(
        _uint_word(0),
        _int_word(1),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(0),
        _uint_word(1),
    )
    mapping = {
        (pm, ArbitrumUniswapV3PositionReader._BALANCE_OF(owner).lower()): _words_hex(
            _uint_word(1)
        ),
        (
            pm,
            ArbitrumUniswapV3PositionReader._TOKEN_OF_OWNER_BY_INDEX(owner, 0).lower(),
        ): _words_hex(_uint_word(7)),
        (pm, ArbitrumUniswapV3PositionReader._POSITIONS(7).lower()): position,
        (
            factory,
            ArbitrumUniswapV3PositionReader._GET_POOL(token0, token1, 3000).lower(),
        ): _words_hex(_address_word(pool)),
        (pool, "0x3850c7bd"): slot0,
        (token0.lower(), "0x313ce567"): _words_hex(_uint_word(6)),
        (token1.lower(), "0x313ce567"): _words_hex(_uint_word(18)),
    }

    async def request_fn(_rpc_url, payload, _timeout):
        params = payload["params"][0]
        key = (str(params["to"]).lower(), str(params["data"]).lower())
        return {"jsonrpc": "2.0", "id": 1, "result": mapping[key]}

    async def price_request_fn(_tokens, _timeout):
        raise RuntimeError("price_down")

    reader = ArbitrumUniswapV3PositionReader(
        rpc_url="https://rpc.local",
        request_fn=request_fn,
        price_request_fn=price_request_fn,
        baseline_provider=_StaticBaselineProvider(),
        now_fn=lambda: 1700000000.0,
    )
    states = _run(reader.load_active_position_states(owner))
    assert len(states) == 1
    state = states[0]
    assert state.unclaimed_fees_usd == 0.0
    assert "STALE_PRICE" in state.metadata.get("fee_reason_codes", [])
    assert state.position_value_usd == 0.0
    assert "STALE_PRICE" in state.metadata.get("valuation_reason_codes", [])


def test_position_reader_raw_amounts_respect_range_state():
    amount0_left, amount1_left = (
        ArbitrumUniswapV3PositionReader._compute_raw_position_amounts(
            liquidity=1_000_000,
            current_tick=-200,
            tick_lower=-100,
            tick_upper=100,
        )
    )
    assert amount0_left > 0.0
    assert amount1_left == 0.0

    amount0_right, amount1_right = (
        ArbitrumUniswapV3PositionReader._compute_raw_position_amounts(
            liquidity=1_000_000,
            current_tick=200,
            tick_lower=-100,
            tick_upper=100,
        )
    )
    assert amount0_right == 0.0
    assert amount1_right > 0.0

    amount0_mid, amount1_mid = (
        ArbitrumUniswapV3PositionReader._compute_raw_position_amounts(
            liquidity=1_000_000,
            current_tick=0,
            tick_lower=-100,
            tick_upper=100,
        )
    )
    assert amount0_mid > 0.0
    assert amount1_mid > 0.0


def test_chain_specific_position_readers_use_expected_defaults():
    base_reader = BaseUniswapV3ChainPositionReader(
        rpc_url="https://base-rpc.local",
        baseline_provider=_StaticBaselineProvider(),
    )
    assert base_reader.chain_name == "Base"
    assert base_reader.position_manager_address == UNISWAP_V3_POSITION_MANAGER_BASE.lower()
    assert base_reader.factory_address == UNISWAP_V3_FACTORY_BASE.lower()

    optimism_reader = OptimismUniswapV3PositionReader(
        rpc_url="https://optimism-rpc.local",
        baseline_provider=_StaticBaselineProvider(),
    )
    assert optimism_reader.chain_name == "Optimism"
    assert (
        optimism_reader.position_manager_address
        == UNISWAP_V3_POSITION_MANAGER_OPTIMISM.lower()
    )
    assert optimism_reader.factory_address == UNISWAP_V3_FACTORY_OPTIMISM.lower()

    hype_reader = HypeEVMUniswapV3PositionReader(
        rpc_url="https://hypeevm-rpc.local",
        baseline_provider=_StaticBaselineProvider(),
    )
    assert hype_reader.chain_name == "HypeEVM"
    assert hype_reader.position_manager_address == UNISWAP_V3_POSITION_MANAGER_HYPEEVM.lower()
    assert hype_reader.factory_address == UNISWAP_V3_FACTORY_HYPEEVM.lower()
