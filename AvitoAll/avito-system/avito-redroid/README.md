# Avito Redroid Masked

Custom Redroid Docker image that masks the container as a random real Android device from GSMArena database.

## Features

- **Random Device Masking**: Selects a random device from 4000+ real devices in GSMArena database
- **Persistent Identity**: Device profile is saved and reused on container restarts
- **Anti-Detection**: Removes emulator traces and sets security properties
- **One-Command Deploy**: Ready for any Linux server with Docker

## Quick Start

### 1. Prerequisites

On the host server, load required kernel modules:

```bash
# Load binder modules (required for Redroid)
sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"
sudo modprobe ashmem_linux  # or ensure CONFIG_ASHMEM=y in kernel
```

### 2. Configure

```bash
# Create environment file
cp .env.example .env
# Edit .env and set DB_PASSWORD
nano .env
```

### 3. Build and Run

```bash
# Build the image
docker compose build

# Start the container
docker compose up -d

# View logs
docker compose logs -f
```

### 4. Access

- **ADB**: `adb connect <server-ip>:5555`
- **Web** (if ws-scrcpy): `http://<server-ip>:8000/`

## Device Management

### View Current Device

```bash
docker exec avito-redroid cat /data/device_profile.json | jq .
```

### Change Device (Get New Random)

```bash
# Remove profile and restart
docker exec avito-redroid rm /data/device_profile.json
docker compose restart
```

### Verify Masking

```bash
adb connect localhost:5555
adb shell getprop ro.product.model      # Should show real device name
adb shell getprop ro.product.brand      # Should show brand (Samsung, etc.)
adb shell getprop ro.kernel.qemu        # Should be 0 or empty
adb shell getprop ro.build.fingerprint  # Should show realistic fingerprint
```

## Structure

```
avito-redroid/
├── docker-compose.yml      # Docker configuration
├── Dockerfile              # Image build instructions
├── entrypoint.sh           # Container entrypoint
├── .env                    # Database credentials (don't commit!)
├── .env.example            # Template for .env
│
├── scripts/                # Python generators
│   ├── device_profile_gen.py   # Selects random device from DB
│   ├── build_prop_gen.py       # Generates build.prop
│   ├── fingerprint_gen.py      # Generates fingerprint
│   └── requirements.txt        # Python dependencies
│
├── init.d/                 # Init scripts
│   ├── 01_apply_mask.sh    # Apply device properties
│   ├── 02_cleanup_emu.sh   # Remove emulator traces
│   └── 03_start_services.sh # Start ADB, etc.
│
├── config/                 # Configuration
│   ├── allowed_brands.json # Allowed brands for random selection
│   └── build.prop.template # Reference template
│
└── output/                 # Output directory (mounted from host)
    ├── tokens/             # Extracted Avito tokens
    └── profiles/           # Profile backups
```

## Database

Device profiles are selected from PostgreSQL database:
- Host: `85.198.98.104:5433`
- Table: `zip_gsmarena_raw`
- ~4000+ real Android devices

### Selection Criteria

- Release year >= 2021 (Android 11+)
- Popular brands: Samsung, Xiaomi, Google, OnePlus, Oppo, Realme, etc.
- Excludes budget models (Lite, Go, Mini, etc.)

## Deploy to New Server

```bash
# 1. Copy to new server
scp -r avito-redroid/ root@new-server:/opt/

# 2. Create .env
ssh root@new-server
echo "DB_PASSWORD=your_password" > /opt/avito-redroid/.env

# 3. Load kernel modules
modprobe binder_linux devices="binder,hwbinder,vndbinder"

# 4. Build and run
cd /opt/avito-redroid
docker compose build
docker compose up -d
```

## Troubleshooting

### Container won't start

Check kernel modules:
```bash
lsmod | grep binder
lsmod | grep ashmem
```

### Database connection fails

Container will use fallback Samsung Galaxy S23 profile if DB is unavailable.

### Device not masked properly

Check logs:
```bash
docker exec avito-redroid cat /data/masking.log
```

## Ports

| Port | Service |
|------|---------|
| 5555 | ADB |
| 8000 | ws-scrcpy web (optional) |

## Volumes

| Volume | Purpose |
|--------|---------|
| `redroid_data:/data` | Android data, device profile, Avito auth |
| `./output:/opt/output` | Tokens and profile backups on host |
