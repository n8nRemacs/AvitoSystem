#!/system/bin/sh
# Clean up emulator detection files and properties
# This script removes traces that apps use to detect emulator environment

MASKING_LOG="/data/masking.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$MASKING_LOG"
    echo "[CLEANUP] $1"
}

log "Starting emulator cleanup..."

# ===========================================
# 1. Remove QEMU/Goldfish device files
# ===========================================
log "Removing emulator device files..."

QEMU_FILES="
/dev/qemu_pipe
/dev/goldfish_pipe
/dev/goldfish_address_space
/dev/goldfish_sync
/dev/socket/qemud
/dev/socket/qemu_pipe
/dev/bus/usb
"

for file in $QEMU_FILES; do
    if [ -e "$file" ]; then
        rm -rf "$file" 2>/dev/null
        log "Removed: $file"
    fi
done

# ===========================================
# 2. Remove QEMU system files
# ===========================================
log "Removing emulator system files..."

QEMU_SYS_FILES="
/sys/qemu_trace
/sys/kernel/debug/qemu_trace
/system/lib/libc_malloc_debug_qemu.so
/system/lib64/libc_malloc_debug_qemu.so
/vendor/lib/libc_malloc_debug_qemu.so
/vendor/lib64/libc_malloc_debug_qemu.so
"

for file in $QEMU_SYS_FILES; do
    if [ -e "$file" ]; then
        rm -rf "$file" 2>/dev/null
        log "Removed: $file"
    fi
done

# ===========================================
# 3. Set emulator-hiding properties
# ===========================================
log "Setting anti-detection properties..."

# Core QEMU properties
setprop ro.kernel.qemu 0
setprop ro.kernel.qemu.gles 0
setprop ro.kernel.android.qemud 0

# Init services (mark as stopped)
setprop init.svc.qemu-props stopped
setprop init.svc.qemu-adb stopped
setprop init.svc.goldfish-setup stopped
setprop init.svc.goldfish-logcat stopped
setprop init.svc.ranchu-setup stopped
setprop init.svc.ranchu-net stopped

# Boot properties
setprop ro.boot.qemu 0
setprop ro.boot.hardware.sku ""

# ===========================================
# 4. Security properties
# ===========================================
log "Setting security properties..."

setprop ro.secure 1
setprop ro.adb.secure 1
setprop ro.debuggable 0
setprop ro.allow.mock.location 0
setprop ro.boot.verifiedbootstate green
setprop ro.boot.flash.locked 1
setprop ro.boot.vbmeta.device_state locked
setprop ro.boot.veritymode enforcing
setprop ro.oem_unlock_supported 0

# ===========================================
# 5. Remove emulator binary signatures
# ===========================================
log "Cleaning emulator binaries..."

EMU_BINS="
/system/bin/qemu-props
/system/bin/qemud
/system/bin/goldfish-setup
/system/bin/goldfish_address_space
/vendor/bin/qemu-props
/vendor/bin/qemud
"

for bin in $EMU_BINS; do
    if [ -e "$bin" ]; then
        mv "$bin" "${bin}.disabled" 2>/dev/null
        log "Disabled: $bin"
    fi
done

# ===========================================
# 6. Clean up /proc indicators
# ===========================================
log "Hiding /proc indicators..."

# Mount point to hide hypervisor info
if [ -d "/proc/cpuinfo" ] 2>/dev/null; then
    log "Note: /proc/cpuinfo modification requires kernel support"
fi

# ===========================================
# 7. Network interface cleanup
# ===========================================
log "Cleaning network interfaces..."

# Remove emulator-specific network interfaces
ip link set eth0 name wlan0 2>/dev/null || true
ip link set eth1 name rmnet0 2>/dev/null || true

# ===========================================
# 8. Sensors cleanup
# ===========================================
log "Configuring sensors..."

# Hide goldfish sensors
setprop ro.hardware.sensors ""
setprop config.disable_sensors 0

# ===========================================
# 9. Build environment cleanup
# ===========================================
log "Cleaning build environment..."

# These properties shouldn't indicate emulator
setprop ro.product.cpu.abi arm64-v8a
setprop ro.product.cpu.abilist arm64-v8a,armeabi-v7a,armeabi
setprop ro.product.cpu.abilist32 armeabi-v7a,armeabi
setprop ro.product.cpu.abilist64 arm64-v8a

# ===========================================
# Done
# ===========================================
log "Emulator cleanup completed successfully"
log "Key settings: qemu=0, secure=1, debuggable=0"
