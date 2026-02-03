---
name: portfolio-schema
description: Define and maintain the internal canonical portfolio schema (positions, assets, chains, protocols) used across adapters and risk checks.
---

# Portfolio Schema

## Goal
Maintain a single canonical schema for portfolio data so all modules (Monitoring/Discovery/Security) can interoperate.

## When to use
- Adding a new adapter (Debank/DeFiLlama/De.Fi/GoPlus)
- Adding a new risk check or report output
- Upgrading JSON report format

## Workflow
1. Define minimal entities:
   - Wallet
   - Position (type: supply/borrow/lp/other)
   - Asset (symbol, address, decimals, chain)
   - Protocol (name, id)
2. Define required fields vs optional fields (unknown allowed).
3. Add a version field to the report root (e.g., `schema_version`).
4. Ensure mappings from adapters are loss-aware:
   - Missing fields are `null`/omitted, never guessed.
5. Update Memory Bank `docs/memory-bank/systemPatterns.md` when schema changes.

## Outputs
- A clear schema definition (pydantic models or JSON schema) and example JSON.
