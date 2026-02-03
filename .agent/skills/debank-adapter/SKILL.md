---
name: debank-adapter
description: Build or update the Debank Cloud adapter (auth, rate limits, retries) and normalize positions into the canonical portfolio schema.
---

# Debank Adapter

## Goal
Implement a robust Debank Cloud client and a normalization layer that produces a canonical portfolio snapshot.

## Workflow
1. Identify required Debank endpoints for:
   - portfolio positions (supply/borrow/lp)
   - chain and protocol metadata (if available)
2. Implement HTTP client:
   - timeouts
   - retries with exponential backoff
   - rate-limit handling
   - structured errors (partial data allowed)
3. Normalize payloads into the canonical schema (use skill `portfolio-schema`).
4. Store representative fixtures (sanitized) and add contract tests.
5. Never log secrets; read from env vars.

## Outputs
- Adapter module + normalization functions
- Fixture-based tests
- Documentation of env vars required
