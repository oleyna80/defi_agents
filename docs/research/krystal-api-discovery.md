# Krystal API Discovery Report

**Date:** 2026-02-19 (updated)
**Author:** Gemini (Tech Lead)
**Status:** ⚠️ **CONDITIONAL GO** — `cloud-api.krystal.app` auth path validated; production gates still open
**Related:** Spec 017 (OQ-6, R-8), Plan 017 (Phase F)
**Superseded by:** [krystal-integration-decision-report.md](krystal-integration-decision-report.md)

---

## 1. What Was Tested

| Probe | Endpoint | Method | Result |
|-------|----------|--------|--------|
| Pool listing | `GET https://api.krystal.app/all/v1/pool/list?chainId=42161&limit=1` | curl, httpx | **403** |
| Pool detail | `GET https://api.krystal.app/all/v1/pool/detail?chainId=42161&address=0xC31E...` | curl | **403** |
| Swagger UI | `GET https://api.krystal.app/swagger` | curl, HTTP fetch | **403** |
| Alt subdomain | `GET https://defi.krystal.app/api/v1/pools?chainId=42161` | curl | **403** |
| Cloud subdomain | `GET https://cloud.krystal.app/api/v1/pools?chainId=42161` | curl | **403** |
| Dev docs | `GET https://developer.krystal.app` | HTTP fetch | **DNS NXDOMAIN** |
| GitBook docs | `GET https://docs.krystal.app/krystal-api/api-reference` | HTTP fetch | **404** |
| Browser UA spoof | `api.krystal.app` with Chrome-like `User-Agent` header | curl | **403** |

## 2. What Blocks Server-Side Access (Wallet API Surface)

The 403 response includes these Cloudflare headers:

```
cf-mitigated: challenge
critical-ch: Sec-CH-UA-Bitness, Sec-CH-UA-Arch, ...
accept-ch: Sec-CH-UA-Bitness, Sec-CH-UA-Arch, ...
```

This is a **Cloudflare Managed Challenge (Turnstile)** — it requires a JavaScript-capable browser to solve. `curl`/`httpx`/`aiohttp` cannot pass this challenge.  
These findings apply to the wallet/front-end API surface (`api.krystal.app`/`defi.krystal.app`/`cloud.krystal.app`), not to `cloud-api.krystal.app`, which is key-authenticated via `KC-APIKey`.

## 3. Implications

| Concern | Assessment |
|---------|------------|
| Server-side `httpx` integration for `api.krystal.app` | ❌ Impossible without Cloudflare bypass |
| Headless browser (Playwright) | ⚠️ Possible but fragile, Cloudflare regularly patches headless detection |
| Server-side integration via `cloud-api.krystal.app` | ✅ Supported with `KC-APIKey` header |
| Tick-level data availability | ❓ Unknown at discovery stage (later confirmed pool-level only in decision report) |

## 4. Remaining Gates Before Production Enablement

Auth-path gate is now closed via `cloud-api.krystal.app` + `KC-APIKey`.  
To integrate Krystal as a discovery provider (REQ-022) in production, we still need:

1. **Schema stability check** — same response shape across at least 2 probes within 48h.
2. **Rate-limit/load profile** — confirm quota and throughput for scheduled scans.
3. **Operational fallback contract** — explicit fallback to DeFiLlama/GeckoTerminal when Krystal is unavailable.

## 5. Recommendation

| Action | Priority | Deadline |
|--------|----------|----------|
| Complete 48h schema-stability probe window (`/v1/pools`) | P0 | +2 days |
| Run light load profile to estimate effective limits/quota | P0 | +3 days |
| **Do not block P0** — proceed with `UniswapV3TickProvider` (Subgraph) as sole tick source | P0 | Immediate |
| If remaining gates fail → keep Krystal disabled and use DeFiLlama/GeckoTerminal discovery fallback | — | +1 week |

## 6. Go/No-Go Status

**Previous status: NO-GO** (based on `api.krystal.app` probes only).

**Updated status: ⚠️ CONDITIONAL GO** — `cloud-api.krystal.app` is a separate API surface with `KC-APIKey` header auth, but production enablement still depends on stability/limit validation. See [decision report](krystal-integration-decision-report.md) for full details.

Conditions for GO (all required):
- [x] Service API key returned 200 from server-side `curl` (**endpoint: `/v1/pools`, header: `KC-APIKey`**)
- [ ] JSON response schema stable across 2+ calls over 48h
- [x] Response includes: `poolAddress`, `token0`, `token1`, `stats30d.volume`, `feeTier`
