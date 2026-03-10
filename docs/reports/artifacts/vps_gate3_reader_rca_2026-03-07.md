# Position Reader RCA (2026-03-07)

## Logs Analysis (48h SHADOW on VPS)

| error_signature | count | first_seen | last_seen | probable_root_cause | fix_candidate |
| --- | --- | --- | --- | --- | --- |
| `POSITION_READER_ALL_CHAINS_FAILED` | 7 | 2026-03-05/06 | 2026-03-07 12:19:50 | Transient RPC timeouts or HTTP 5XX/429 errors from public endpoints. The `_post_json` method in `BaseUniswapV3PositionReader` has no retry mechanism, leading to immediate failure of all networks if transient network drops occur.  | Implement short retry loop in `_post_json` with a backoff strategy (e.g., 3 attempts, exponential backoff) to handle transient failures without increasing cycle timeout excessively. |
| `Traceback\|CRITICAL` (`RuntimeError: POSITION_READER_ALL_CHAINS_FAILED`) | 3 | 2026-03-05/06 | 2026-03-07 12:19:50 | `run_sentinel_cycle` in `main.py` does not explicitly catch `POSITION_READER_ALL_CHAINS_FAILED` raised by `_load_execution_states`, causing the unhandled exception to bubble up, crashing the daemon. | Add a targeted `except RuntimeError` in `main.py` around `_load_execution_states` to gracefully log the degradation and skip the execution loop, rather than tearing down the entire process. |
| `PositionReaderError` | numerous | - | - | Exception logging in `main.py` uses `exc.__class__.__name__` instead of extracting the specific reason code, masking underlying RPC failures. | Modify `main.py` to extract and log `getattr(exc, "reason_code", exc.__class__.__name__)` for improved observability. |
