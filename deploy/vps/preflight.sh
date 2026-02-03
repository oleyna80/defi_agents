#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

status_ok() { echo "[OK] $1"; }
status_warn() { echo "[WARN] $1"; }
status_fail() { echo "[FAIL] $1"; exit 1; }

[[ -f .env ]] || status_fail ".env not found at project root"
status_ok ".env exists"

required=(DEEPSEEK_API_KEY TELEGRAM_BOT_TOKEN)
for key in "${required[@]}"; do
    if grep -Eq "^${key}=.+" .env; then
        status_ok "$key is set"
    else
        status_fail "$key is missing in .env"
    fi
done

if grep -iE "^[[:space:]]*ALLOW_MOCK_FALLBACK[[:space:]]*=[[:space:]]*['\"]?true['\"]?([[:space:]]*$|[[:space:]]+#)" .env >/dev/null; then
    status_fail "ALLOW_MOCK_FALLBACK is TRUE. Production must be strict (false)."
fi
status_ok "ALLOW_MOCK_FALLBACK is production-safe"

[[ -f requirements.txt ]] && status_ok "requirements.txt exists" || status_fail "requirements.txt missing"
[[ -f main.py ]] && status_ok "main.py exists" || status_fail "main.py missing"
[[ -f deploy/systemd/defi-sentinel.service ]] && status_ok "systemd service template exists" || status_fail "service template missing"
[[ -f deploy/systemd/defi-sentinel.timer ]] && status_ok "systemd timer template exists" || status_fail "timer template missing"

if command -v python3 >/dev/null 2>&1; then
    status_ok "python3 available: $(python3 --version)"
else
    status_fail "python3 not found"
fi

if command -v dig >/dev/null 2>&1; then
    domain=$(grep -E '^APP_DOMAIN=' .env | cut -d '=' -f2- | tr -d '"' || true)
    if [[ -n "${domain}" ]]; then
        if dig +short "$domain" | grep -Eq '.'; then
            status_ok "DNS resolves for APP_DOMAIN=$domain"
        else
            status_warn "APP_DOMAIN=$domain does not resolve yet"
        fi
    else
        status_warn "APP_DOMAIN not set in .env (skip DNS check)"
    fi
else
    status_warn "dig not found (skip DNS check)"
fi

echo "Preflight completed."
