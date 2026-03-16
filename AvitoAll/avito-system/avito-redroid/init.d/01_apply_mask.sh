#!/system/bin/sh
# Apply device mask from generated build.prop
# This script runs during Android init

PROFILE_FILE="/data/device_profile.json"
BUILD_PROP_BACKUP="/data/build.prop.original"
MASKING_LOG="/data/masking.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$MASKING_LOG"
    echo "[MASK] $1"
}

log "Starting device mask application..."

# Check if profile exists
if [ ! -f "$PROFILE_FILE" ]; then
    log "ERROR: Device profile not found at $PROFILE_FILE"
    exit 1
fi

# Apply key properties using setprop
log "Applying device properties..."

# Read values from profile (using simple grep/cut for shell)
BRAND=$(grep '"brand"' "$PROFILE_FILE" | cut -d'"' -f4)
MODEL=$(grep '"model"' "$PROFILE_FILE" | cut -d'"' -f4)
DEVICE=$(grep '"device"' "$PROFILE_FILE" | cut -d'"' -f4)
PRODUCT=$(grep '"product"' "$PROFILE_FILE" | cut -d'"' -f4)
MANUFACTURER=$(grep '"manufacturer"' "$PROFILE_FILE" | cut -d'"' -f4)
HARDWARE=$(grep '"hardware"' "$PROFILE_FILE" | cut -d'"' -f4)
FINGERPRINT=$(grep '"fingerprint"' "$PROFILE_FILE" | cut -d'"' -f4)
ANDROID_VERSION=$(grep '"android_version"' "$PROFILE_FILE" | cut -d'"' -f4)
SDK_VERSION=$(grep '"sdk_version"' "$PROFILE_FILE" | cut -d'"' -f4)
BUILD_ID=$(grep '"build_id"' "$PROFILE_FILE" | cut -d'"' -f4)
BUILD_NUMBER=$(grep '"build_number"' "$PROFILE_FILE" | cut -d'"' -f4)
SECURITY_PATCH=$(grep '"security_patch"' "$PROFILE_FILE" | cut -d'"' -f4)

log "Masking as: $BRAND $MODEL"

# Product properties
setprop ro.product.model "$MODEL"
setprop ro.product.brand "$BRAND"
setprop ro.product.name "$PRODUCT"
setprop ro.product.device "$DEVICE"
setprop ro.product.manufacturer "$MANUFACTURER"
setprop ro.product.board "$HARDWARE"

# System product properties
setprop ro.product.system.brand "$BRAND"
setprop ro.product.system.device "$DEVICE"
setprop ro.product.system.manufacturer "$MANUFACTURER"
setprop ro.product.system.model "$MODEL"
setprop ro.product.system.name "$PRODUCT"

# Vendor product properties
setprop ro.product.vendor.brand "$BRAND"
setprop ro.product.vendor.device "$DEVICE"
setprop ro.product.vendor.manufacturer "$MANUFACTURER"
setprop ro.product.vendor.model "$MODEL"
setprop ro.product.vendor.name "$PRODUCT"

# Build properties
setprop ro.build.id "$BUILD_ID"
setprop ro.build.display.id "$BUILD_NUMBER"
setprop ro.build.version.incremental "$BUILD_NUMBER"
setprop ro.build.version.sdk "$SDK_VERSION"
setprop ro.build.version.release "$ANDROID_VERSION"
setprop ro.build.version.security_patch "$SECURITY_PATCH"
setprop ro.build.type "user"
setprop ro.build.tags "release-keys"
setprop ro.build.flavor "${PRODUCT}-user"
setprop ro.build.product "$DEVICE"

# Fingerprint (critical for detection)
setprop ro.build.fingerprint "$FINGERPRINT"
setprop ro.bootimage.build.fingerprint "$FINGERPRINT"
setprop ro.vendor.build.fingerprint "$FINGERPRINT"
setprop ro.system.build.fingerprint "$FINGERPRINT"

# Hardware
setprop ro.hardware "$HARDWARE"
setprop ro.hardware.chipname "$HARDWARE"
setprop ro.board.platform "$HARDWARE"

log "Device properties applied successfully"
log "Fingerprint: $FINGERPRINT"
