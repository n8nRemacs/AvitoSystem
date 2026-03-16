#!/system/bin/sh
# cleanup_emulator.sh
# Init script to remove emulator traces from Redroid container
# This script runs at container startup to mask the emulator as a real device

# Remove emulator-specific device nodes
rm -f /dev/socket/qemud
rm -f /dev/qemu_pipe
rm -f /dev/goldfish*
rm -f /sys/qemu_trace

# Remove Genymotion traces (if any)
rm -f /dev/socket/genyd
rm -f /dev/socket/baseband_genyd

# Remove VirtualBox traces
rm -f /sys/devices/virtual/dmi/id/product_name
rm -f /sys/devices/virtual/dmi/id/sys_vendor

# Wait for system to fully boot
sleep 5

# Optional: Kill logcat to reduce detection surface
# pkill logcat

# Log completion
echo "Emulator cleanup completed" > /data/local/tmp/cleanup.log
