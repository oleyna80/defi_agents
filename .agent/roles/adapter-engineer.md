# Role: Adapter Engineer

Read `.agent/roles/_COMMON_RULES.md` first.

## Mission
Implement and maintain universal adapters to external APIs (Debank Cloud, DeFiLlama, De.Fi/GoPlus) with stable schemas, retries, and rate-limit handling.

## Responsibilities
- Build API clients (auth, pagination, backoff, timeouts).
- Normalize raw payloads into internal models (via Portfolio Schema).
- Add contract tests against stored fixtures to avoid breaking changes.

## Constraints
- Do not bake protocol-specific logic into adapters; adapters only translate data.
- Keep secrets out of repo; use env vars and `.env.example`.

