#!/bin/bash
# Avito Telegram Bridge - Deployment Script
# Run: bash deploy.sh

set -e

echo "========================================"
echo "  Avito Bridge v2 - Auto Deployment"
echo "========================================"

# Determine script directory (where bot files are)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[*] Bot directory: $SCRIPT_DIR"

# Check required files exist
if [ ! -f "$SCRIPT_DIR/avito_telegram_bot_v2.py" ]; then
    echo "[!] ERROR: avito_telegram_bot_v2.py not found!"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/avito_session_new.json" ]; then
    echo "[!] ERROR: avito_session_new.json not found!"
    exit 1
fi

# Install dependencies
echo ""
echo "[*] Installing Python dependencies..."
pip3 install aiohttp --quiet 2>/dev/null || pip install aiohttp --quiet

# Stop old bot if running
echo ""
echo "[*] Stopping old processes..."
pkill -f "avito_telegram_bot" 2>/dev/null || true
systemctl stop avito-bridge 2>/dev/null || true

# Create systemd service
echo ""
echo "[*] Creating systemd service..."

cat > /etc/systemd/system/avito-bridge.service << EOF
[Unit]
Description=Avito Telegram Bridge v2
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/avito_telegram_bot_v2.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/avito-bridge.log
StandardError=append:/var/log/avito-bridge.log

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

echo "[+] Service file created: /etc/systemd/system/avito-bridge.service"

# Reload and start
echo ""
echo "[*] Starting service..."
systemctl daemon-reload
systemctl enable avito-bridge
systemctl start avito-bridge

# Wait and check status
sleep 3
echo ""
echo "========================================"
echo "  Deployment Complete!"
echo "========================================"
echo ""

if systemctl is-active --quiet avito-bridge; then
    echo "[+] Status: RUNNING"
    echo ""
    echo "Useful commands:"
    echo "  systemctl status avito-bridge    # Check status"
    echo "  systemctl restart avito-bridge   # Restart"
    echo "  journalctl -u avito-bridge -f    # View logs"
    echo "  tail -f /var/log/avito-bridge.log"
    echo ""
    echo "Now send /start to @avitorevers_bot in Telegram!"
else
    echo "[!] Status: FAILED"
    echo ""
    echo "Check logs:"
    echo "  journalctl -u avito-bridge -n 50"
    systemctl status avito-bridge --no-pager
fi
