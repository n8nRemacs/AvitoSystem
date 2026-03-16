# Anti-Emulator Masking Scripts

## Overview

These scripts help Redroid containers bypass Avito's `libfp.so` anti-emulator detection checks.

## cleanup_emulator.sh

**Purpose:** Remove emulator-specific device files and traces at container startup.

**What it removes:**

1. **QEMU traces:**
   - `/dev/socket/qemud` - QEMU daemon socket
   - `/dev/qemu_pipe` - QEMU pipe interface (main detection vector)
   - `/dev/goldfish*` - Goldfish emulator devices
   - `/sys/qemu_trace` - QEMU trace interface

2. **Genymotion traces:**
   - `/dev/socket/genyd`
   - `/dev/socket/baseband_genyd`

3. **VirtualBox traces:**
   - `/sys/devices/virtual/dmi/id/product_name`
   - `/sys/devices/virtual/dmi/id/sys_vendor`

**How it's used:**

Mounted as read-only init script in docker-compose.yml:
```yaml
volumes:
  - ./scripts/cleanup_emulator.sh:/system/bin/cleanup.sh:ro
```

**Execution timing:**

The script runs at container startup and waits 5 seconds for the system to fully boot before completing.

## Anti-Emulator Checks Bypassed

Avito's `libfp.so` performs these checks (all now passing):

| Check | Method | Status |
|-------|--------|--------|
| QEMU detection | `/dev/qemu_pipe` existence | ✅ Removed by script |
| Kernel QEMU flag | `ro.kernel.qemu` property | ✅ Set to `0` in docker-compose |
| Build fingerprint | `Build.FINGERPRINT` contains "generic" | ✅ Real device fingerprints |
| Hardware name | `ro.hardware` = "goldfish" | ✅ Real hardware (qcom, exynos) |
| Manufacturer | `Build.MANUFACTURER` = "unknown" | ✅ Real manufacturers |
| CPU architecture | `/proc/cpuinfo` | ✅ ARM platform |
| Goldfish devices | `/dev/goldfish*` | ✅ Removed by script |

## Testing the Masking

After starting a container:

```bash
# Connect to container
adb connect localhost:5555

# Check build properties
adb shell getprop ro.kernel.qemu
# Should output: 0

adb shell getprop ro.hardware
# Should output: qcom (or exynos2100, gs101)

# Check for emulator traces
adb shell ls /dev/qemu_pipe
# Should output: No such file or directory

adb shell ls /dev/goldfish*
# Should output: No such file or directory

# Verify cleanup log
adb shell cat /data/local/tmp/cleanup.log
# Should output: Emulator cleanup completed
```

## Important Notes

1. **ARM platform is critical** - x86 emulators will be detected even with perfect masking
2. **Init script must run before Avito app starts** - that's why we use volume mount
3. **Build properties in docker-compose.yml must match real devices** - use fingerprints from actual phones
4. **SELinux permissive mode** required for init script execution

## Debugging

If Avito still detects emulator:

1. Check if cleanup script ran:
   ```bash
   adb shell cat /data/local/tmp/cleanup.log
   ```

2. Verify build properties:
   ```bash
   adb shell getprop | grep -E "(qemu|goldfish|emulator)"
   ```

3. Check for remaining emulator files:
   ```bash
   adb shell find /dev -name "*qemu*" -o -name "*goldfish*"
   ```

4. Inspect libfp.so behavior (requires root):
   ```bash
   adb shell su -c "logcat | grep -i 'fp\|emulator\|virtual'"
   ```

## References

- Redroid documentation: https://github.com/remote-android/redroid-doc
- Android build properties: https://source.android.com/docs/core/architecture/configuration/add-system-properties
- QEMU detection methods: https://github.com/ShiftLeftSecurity/anti-emulation
