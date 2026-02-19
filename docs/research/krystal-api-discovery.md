# Krystal API Discovery Report

**Date:** 2026-02-19 (updated)
**Author:** Gemini (Tech Lead)
**Status:** ✅ **RESOLVED** — `cloud-api.krystal.app` validated with `KC-APIKey` header
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

## 2. What Blocks Server-Side Access

The 403 response includes these Cloudflare headers:

```
cf-mitigated: challenge
critical-ch: Sec-CH-UA-Bitness, Sec-CH-UA-Arch, ...
accept-ch: Sec-CH-UA-Bitness, Sec-CH-UA-Arch, ...
```

This is a **Cloudflare Managed Challenge (Turnstile)** — it requires a JavaScript-capable browser to solve. `curl`/`httpx`/`aiohttp` cannot pass this challenge. This is **not** an API-key-based restriction; it's a WAF-level bot mitigation.

## 3. Implications

| Concern | Assessment |
|---------|------------|
| Server-side `httpx` integration | ❌ Impossible without Cloudflare bypass |
| Headless browser (Playwright) | ⚠️ Possible but fragile, Cloudflare regularly patches headless detection |
| Service API key / IP allowlist | ❓ Unknown — requires contact with Krystal team |
| Tick-level data availability | ❓ Unknown — Swagger shows `/pool/list` endpoint but tick distribution endpoint unconfirmed |

## 4. Minimum Required Inputs to Unblock

To integrate Krystal as a discovery provider (REQ-022), we need **one** of:

1. **Service API key** — a dedicated key that bypasses Cloudflare challenge (e.g., `Authorization: Bearer <key>` or `x-api-key` header). Requires partnership / developer program enrollment.
2. **Server IP allowlist** — Krystal adds our VPS IP to their Cloudflare WAF exception list.
3. **Alternative API base URL** — some aggregators expose a separate `api-v2` or `internal` endpoint without WAF for approved integrators.

## 5. Recommendation

| Action | Priority | Deadline |
|--------|----------|----------|
| Contact Krystal team (support/partnerships) asking for service API access | P1 | +1 week |
| Check if Krystal has a Discord/Telegram dev channel with API docs | P1 | +3 days |
| **Do not block P0** — proceed with `UniswapV3TickProvider` (Subgraph) as sole tick source | P0 | Immediate |
| If no auth path within 2 weeks → close Krystal workstream, DeFiLlama remains sole discovery | — | +2 weeks |

## 6. Go/No-Go Status

**Previous status: NO-GO** (based on `api.krystal.app` probes only).

**Updated status: ✅ GO** — `cloud-api.krystal.app` is a separate API surface with `KC-APIKey` header auth. See [decision report](krystal-integration-decision-report.md) for full validation results.

Conditions for GO (all required):
- [x] Service API key returned 200 from server-side `curl` (**endpoint: `/v1/pools`, header: `KC-APIKey`**)
- [ ] JSON response schema stable across 2+ calls over 48h
- [x] Response includes: `poolAddress`, `token0`, `token1`, `stats30d.volume`, `feeTier`
