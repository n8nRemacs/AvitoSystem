#!/bin/bash
# Token Farm Setup Script
# Run on ARM server (Hetzner CAX, Oracle Ampere)

set -e

echo "=== Token Farm Setup ==="

# Check architecture
ARCH=$(uname -m)
if [[ "$ARCH" != "aarch64" ]]; then
    echo "Warning: This script is designed for ARM64 servers"
    echo "Current architecture: $ARCH"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system..."
apt-get update && apt-get upgrade -y

# Install Docker
echo "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $USER
fi

# Install Docker Compose
echo "Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi

# Install ADB (for container debugging)
echo "Installing ADB..."
apt-get install -y android-tools-adb

# Create directories
echo "Creating directories..."
mkdir -p /opt/avito-farm
mkdir -p /opt/avito-farm/data

# Copy files
echo "Copying files..."
cp -r ../token-farm/* /opt/avito-farm/
cp -r ../shared /opt/avito-farm/

# Create .env if not exists
if [ ! -f /opt/avito-farm/.env ]; then
    cp ../.env.example /opt/avito-farm/.env
    echo "Created .env file. Please edit it with your settings."
fi

# Enable kernel modules for Redroid
echo "Configuring kernel modules..."
modprobe binder_linux devices="binder,hwbinder,vndbinder"
modprobe ashmem_linux

# Add to startup
cat > /etc/modules-load.d/redroid.conf << EOF
binder_linux
ashmem_linux
EOF

# Create systemd service
cat > /etc/systemd/system/avito-farm.service << EOF
[Unit]
Description=Avito Token Farm
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/avito-farm
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable service
systemctl daemon-reload
systemctl enable avito-farm

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit /opt/avito-farm/.env with your settings"
echo "2. Start: systemctl start avito-farm"
echo "3. Check: docker compose logs -f"
echo ""
echo "API will be available at http://localhost:8000"
