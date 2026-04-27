#!/usr/bin/env bash
# Session preflight для AvitoSystem.
# Запускается через SessionStart hook из .claude/settings.json.
# Идемпотентно — повторный запуск не дублирует туннели.

set +e   # не падать на первой же ошибке, проверяем всё

REPORT=""
WARN_COUNT=0

step() {
    local status="$1"  # ok | warn | err
    local msg="$2"
    case "$status" in
        ok)   REPORT+="✅ ${msg}"$'\n' ;;
        warn) REPORT+="⚠️  ${msg}"$'\n'; WARN_COUNT=$((WARN_COUNT + 1)) ;;
        err)  REPORT+="❌ ${msg}"$'\n'; WARN_COUNT=$((WARN_COUNT + 1)) ;;
    esac
}

# ------------------------------------------------------------------
# 1. SOCKS5 tunnel to homelab
# ------------------------------------------------------------------
TUNNEL_IP=$(curl -s --max-time 3 --socks5-hostname 127.0.0.1:1081 https://ifconfig.me 2>/dev/null)

if [ "$TUNNEL_IP" = "213.108.170.194" ]; then
    step ok "SOCKS5 tunnel UP — homelab IP $TUNNEL_IP"
else
    # Попробовать поднять
    ssh -o BatchMode=yes -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
        -o ConnectTimeout=10 -D 127.0.0.1:1081 -N -f homelab 2>/dev/null

    sleep 1
    TUNNEL_IP=$(curl -s --max-time 3 --socks5-hostname 127.0.0.1:1081 https://ifconfig.me 2>/dev/null)

    if [ "$TUNNEL_IP" = "213.108.170.194" ]; then
        step ok "SOCKS5 tunnel запущен — homelab IP $TUNNEL_IP"
    else
        step err "SOCKS5 tunnel НЕ ПОДНЯЛСЯ. Проверь ssh homelab (см. DOCS/RU_PROXY_SETUP.md). Avito-запросы будут получать 429 с зарубежного IP."
    fi
fi

# ------------------------------------------------------------------
# 2. Docker Desktop
# ------------------------------------------------------------------
if docker info >/dev/null 2>&1; then
    step ok "Docker Desktop запущен"
else
    step warn "Docker Desktop не запущен — нужен для локального Postgres+Redis. Запусти Docker Desktop вручную."
fi

# ------------------------------------------------------------------
# 3. uv (Python package manager)
# ------------------------------------------------------------------
UV_VERSION=$(uv --version 2>/dev/null)
if [ -n "$UV_VERSION" ]; then
    step ok "uv установлен ($UV_VERSION)"
else
    step warn "uv не установлен — нужен для управления зависимостями монорепо. Установи: pip install uv"
fi

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
HEADER="=== AvitoSystem session preflight ==="
echo "$HEADER"
echo -n "$REPORT"

if [ "$WARN_COUNT" -gt 0 ]; then
    echo "===== $WARN_COUNT предупреждений — см. выше ====="
else
    echo "===== Всё готово к работе ====="
fi
