#!/bin/bash
# MCP Server Setup Script
# Run on VPS (Hetzner CX22, etc.)

set -e

echo "=== MCP Server Setup ==="

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

# Create directories
echo "Creating directories..."
mkdir -p /opt/avito-mcp
mkdir -p /opt/avito-mcp/data

# Copy files
echo "Copying files..."
cp -r ../mcp-server/* /opt/avito-mcp/
cp -r ../shared /opt/avito-mcp/
cp docker-compose.mcp.yml /opt/avito-mcp/docker-compose.yml
cp Dockerfile.mcp /opt/avito-mcp/

# Create .env if not exists
if [ ! -f /opt/avito-mcp/.env ]; then
    cp ../.env.example /opt/avito-mcp/.env
    echo "Created .env file. Please edit it with your settings."
fi

# Create systemd service
cat > /etc/systemd/system/avito-mcp.service << EOF
[Unit]
Description=Avito MCP Server
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/avito-mcp
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable service
systemctl daemon-reload
systemctl enable avito-mcp

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "1. Edit /opt/avito-mcp/.env with your settings"
echo "   - Set TELEGRAM_BOT_TOKEN"
echo "   - Set FARM_API_URL to Token Farm address"
echo "2. Start: systemctl start avito-mcp"
echo "3. Check: docker compose logs -f"
echo ""
echo "Bot will start polling Telegram automatically"
