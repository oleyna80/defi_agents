from __future__ import annotations

import os

# Single source of truth for L3 cache invalidation/versioning.
EXTRACTOR_VERSION = "v1.0"
L3_POLICY_VERSION = "v1.0"

# L3 policy thresholds (Plan 008 v3.1).
CONFIDENCE_PASS = 0.80
CONFIDENCE_WARN = 0.65
CONFIDENCE_REJECT = 0.75

# Cache TTLs.
L3_CONTENT_CACHE_TTL_SECONDS = 24 * 60 * 60
L3_ANALYSIS_CACHE_TTL_SECONDS = 72 * 60 * 60

# Extractor hard cap.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024  # 4MB


def should_allow_mock_fallback() -> bool:
    """Lazy env check so .env can be loaded before evaluating this flag."""
    return os.getenv("ALLOW_MOCK_FALLBACK", "false").lower() == "true"
