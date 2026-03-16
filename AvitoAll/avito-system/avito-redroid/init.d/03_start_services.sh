#!/system/bin/sh
# Start additional services after Android boot
# Handles ws-scrcpy, ADB configuration, etc.

MASKING_LOG="/data/masking.log"
WS_SCRCPY_DIR="/opt/ws-scrcpy"
WS_SCRCPY_PORT=8000

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$MASKING_LOG"
    echo "[SERVICES] $1"
}

log "Starting additional services..."

# ===========================================
# 1. Configure ADB
# ===========================================
log "Configuring ADB..."

# Enable ADB over TCP
setprop service.adb.tcp.port 5555

# Restart ADB daemon
stop adbd 2>/dev/null || true
start adbd 2>/dev/null || true

log "ADB configured on port 5555"

# ===========================================
# 2. Start ws-scrcpy (if available)
# ===========================================
if [ -d "$WS_SCRCPY_DIR" ] && [ -f "$WS_SCRCPY_DIR/dist/index.js" ]; then
    log "Starting ws-scrcpy on port $WS_SCRCPY_PORT..."

    # Check if node is available
    if command -v node >/dev/null 2>&1; then
        cd "$WS_SCRCPY_DIR"

        # Kill any existing instance
        pkill -f "ws-scrcpy" 2>/dev/null || true

        # Start ws-scrcpy in background
        nohup node dist/index.js --port $WS_SCRCPY_PORT > /data/ws-scrcpy.log 2>&1 &

        sleep 2

        if pgrep -f "ws-scrcpy" > /dev/null; then
            log "ws-scrcpy started successfully"
        else
            log "WARNING: ws-scrcpy failed to start"
        fi
    else
        log "WARNING: Node.js not found, ws-scrcpy not started"
    fi
else
    log "ws-scrcpy not installed, skipping"
fi

# ===========================================
# 3. Network configuration
# ===========================================
log "Configuring network..."

# Set DNS (Google DNS as fallback)
setprop net.dns1 8.8.8.8
setprop net.dns2 8.8.4.4

# ===========================================
# 4. Display configuration
# ===========================================
log "Configuring display..."

# Read display settings from environment or use defaults
DISPLAY_WIDTH=${REDROID_WIDTH:-1080}
DISPLAY_HEIGHT=${REDROID_HEIGHT:-2400}
DISPLAY_DPI=${REDROID_DPI:-420}

log "Display: ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT} @ ${DISPLAY_DPI}dpi"

# ===========================================
# 5. Post-boot status
# ===========================================
log "Services startup completed"

# Print device info
DEVICE_MODEL=$(getprop ro.product.model)
DEVICE_BRAND=$(getprop ro.product.brand)
ANDROID_VER=$(getprop ro.build.version.release)

log "Device: $DEVICE_BRAND $DEVICE_MODEL"
log "Android: $ANDROID_VER"

# ===========================================
# 6. Create status file
# ===========================================
STATUS_FILE="/data/ready"
cat > "$STATUS_FILE" << EOF
{
  "status": "ready",
  "timestamp": "$(date -Iseconds)",
  "device": "$DEVICE_BRAND $DEVICE_MODEL",
  "android": "$ANDROID_VER",
  "adb_port": 5555,
  "ws_scrcpy_port": $WS_SCRCPY_PORT
}
EOF

log "Container ready. Status file: $STATUS_FILE"
