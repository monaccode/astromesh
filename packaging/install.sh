#!/usr/bin/env bash
set -euo pipefail

# Astromesh OS installation script
# Usage: sudo bash install.sh

ASTROMESH_USER="astromesh"
ASTROMESH_GROUP="astromesh"

echo "=== Astromesh OS Installer ==="

# Check root
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (sudo)."
    exit 1
fi

# Create system user
if ! id -u "$ASTROMESH_USER" &>/dev/null; then
    echo "Creating system user: $ASTROMESH_USER"
    useradd --system --no-create-home --shell /usr/sbin/nologin "$ASTROMESH_USER"
fi

# Create directories
echo "Creating directories..."
mkdir -p /etc/astromesh/agents
mkdir -p /etc/astromesh/rag
mkdir -p /var/lib/astromesh/models
mkdir -p /var/lib/astromesh/memory
mkdir -p /var/lib/astromesh/data
mkdir -p /var/log/astromesh/audit
mkdir -p /opt/astromesh/bin
mkdir -p /opt/astromesh/lib

# Set permissions
echo "Setting permissions..."
chown root:$ASTROMESH_GROUP /etc/astromesh -R
chmod 750 /etc/astromesh -R
chown $ASTROMESH_USER:$ASTROMESH_GROUP /var/lib/astromesh -R
chmod 755 /var/lib/astromesh -R
chown $ASTROMESH_USER:$ASTROMESH_GROUP /var/log/astromesh -R
chmod 755 /var/log/astromesh -R

# Copy config if not present
if [[ ! -f /etc/astromesh/runtime.yaml ]]; then
    echo "Installing default configuration..."
    cp -n config/runtime.yaml /etc/astromesh/ 2>/dev/null || true
    cp -n config/providers.yaml /etc/astromesh/ 2>/dev/null || true
    cp -n config/channels.yaml /etc/astromesh/ 2>/dev/null || true
    cp -rn config/agents/* /etc/astromesh/agents/ 2>/dev/null || true
fi

# Install systemd service
echo "Installing systemd service..."
cp packaging/systemd/astromeshd.service /etc/systemd/system/
systemctl daemon-reload

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit /etc/astromesh/runtime.yaml"
echo "  2. Configure providers in /etc/astromesh/providers.yaml"
echo "  3. Add agents to /etc/astromesh/agents/"
echo "  4. Start the daemon: systemctl start astromeshd"
echo "  5. Enable on boot: systemctl enable astromeshd"
echo "  6. Check status: astromeshctl status"
