#!/bin/bash
# Entrypoint for Avito Redroid Masked Container
# Handles device profile generation and mask application before starting Android

set -e

echo "=========================================="
echo "  Avito Redroid Masked Container"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# Configuration
PROFILE_FILE="/data/device_profile.json"
PROFILES_BACKUP_DIR="/opt/output/profiles"
LOG_FILE="/data/masking.log"

# Ensure directories exist
mkdir -p "$(dirname "$PROFILE_FILE")"
mkdir -p "$PROFILES_BACKUP_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# ===========================================
# Step 1: Device Profile Generation
# ===========================================
log "[1/5] Checking device profile..."

if [ ! -f "$PROFILE_FILE" ]; then
    log "First run detected - generating random device profile from GSMArena DB..."

    # Check if DB credentials are set
    if [ -z "$GSMARENA_DB_PASSWORD" ]; then
        log "WARNING: GSMARENA_DB_PASSWORD not set!"
        log "Using fallback profile generation..."

        # Fallback: Generate a default Samsung profile without DB
        cat > "$PROFILE_FILE" << 'FALLBACK_EOF'
{
  "brand": "Samsung",
  "model": "Galaxy S23",
  "device": "dm1q",
  "product": "dm1qxx",
  "manufacturer": "samsung",
  "hardware": "qcom",
  "chipset": "Snapdragon 8 Gen 2",
  "cpu": "Octa-core",
  "android_version": "13",
  "sdk_version": "33",
  "build_id": "TP1A.220624.014",
  "build_number": "S911BXXU2AWA1",
  "security_patch": "2024-10-01",
  "fingerprint": "samsung/dm1qxx/dm1q:13/TP1A.220624.014/S911BXXU2AWA1:user/release-keys",
  "release_year": 2023,
  "source": "fallback"
}
FALLBACK_EOF
        log "Fallback profile created"
    else
        # Generate profile from GSMArena database
        python3 /opt/masking/device_profile_gen.py \
            --db-host "${GSMARENA_DB_HOST}" \
            --db-port "${GSMARENA_DB_PORT}" \
            --db-user "${GSMARENA_DB_USER}" \
            --db-password "${GSMARENA_DB_PASSWORD}" \
            --db-name "${GSMARENA_DB_NAME}" \
            --output "$PROFILE_FILE"

        if [ $? -ne 0 ]; then
            log "ERROR: Failed to generate device profile from DB!"
            exit 1
        fi
    fi

    # Backup the profile
    BACKUP_NAME="$(date +%Y%m%d_%H%M%S)_profile.json"
    cp "$PROFILE_FILE" "$PROFILES_BACKUP_DIR/$BACKUP_NAME"
    log "Profile backed up to: $PROFILES_BACKUP_DIR/$BACKUP_NAME"

else
    log "Using existing device profile..."
fi

# Display current profile
if [ -f "$PROFILE_FILE" ]; then
    DEVICE_BRAND=$(python3 -c "import json; d=json.load(open('$PROFILE_FILE')); print(d.get('brand', 'Unknown'))")
    DEVICE_MODEL=$(python3 -c "import json; d=json.load(open('$PROFILE_FILE')); print(d.get('model', 'Unknown'))")
    log "Device: $DEVICE_BRAND $DEVICE_MODEL"
fi

# ===========================================
# Step 2: Generate build.prop
# ===========================================
log "[2/5] Generating build.prop from profile..."

BUILD_PROP_FILE="/data/custom_build.prop"

python3 /opt/masking/build_prop_gen.py \
    --profile "$PROFILE_FILE" \
    --output "$BUILD_PROP_FILE"

if [ $? -ne 0 ]; then
    log "ERROR: Failed to generate build.prop!"
    exit 1
fi

log "build.prop generated at: $BUILD_PROP_FILE"

# ===========================================
# Step 3: Prepare emulator cleanup
# ===========================================
log "[3/5] Preparing emulator cleanup..."

# Make cleanup script executable
chmod +x /system/etc/init.d/02_cleanup_emu.sh 2>/dev/null || true

log "Cleanup script prepared"

# ===========================================
# Step 4: Set environment for Android
# ===========================================
log "[4/5] Setting Android environment..."

# Export display settings
export DISPLAY_WIDTH="${REDROID_WIDTH:-1080}"
export DISPLAY_HEIGHT="${REDROID_HEIGHT:-2400}"
export DISPLAY_DPI="${REDROID_DPI:-420}"

log "Display: ${DISPLAY_WIDTH}x${DISPLAY_HEIGHT} @ ${DISPLAY_DPI}dpi"

# ===========================================
# Step 5: Start Android
# ===========================================
log "[5/5] Starting Android..."
echo "=========================================="
log "Container startup complete"
log "Device masking active: $DEVICE_BRAND $DEVICE_MODEL"
echo ""
echo "Access points:"
echo "  - ADB: adb connect <host>:5555"
echo "  - Web: http://<host>:8000/ (if ws-scrcpy installed)"
echo ""
echo "To change device, run:"
echo "  docker exec avito-redroid rm /data/device_profile.json"
echo "  docker compose restart"
echo ""
echo "=========================================="

# Pass control to the original Redroid init
# The /init will start Android with our modified properties
exec /init "$@"
