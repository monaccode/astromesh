#!/usr/bin/env bash
set -euo pipefail

echo "Installing Astromesh Node for macOS..."

INSTALL_DIR="/usr/local/opt/astromesh"
CONFIG_DIR="/Library/Application Support/Astromesh/config"
DATA_DIR="/Library/Application Support/Astromesh/data"
LOG_DIR="/Library/Logs/Astromesh"

# Create directories
for dir in "$CONFIG_DIR" "$DATA_DIR/models" "$DATA_DIR/memory" "$DATA_DIR/data" "$LOG_DIR"; do
    mkdir -p "$dir"
done

# Copy venv
if [ -d "venv" ]; then
    mkdir -p "$INSTALL_DIR"
    cp -R venv "$INSTALL_DIR/venv"
    echo "Installed venv to $INSTALL_DIR/venv"
fi

# Symlink binaries
ln -sf "$INSTALL_DIR/venv/bin/astromeshd" /usr/local/bin/astromeshd
ln -sf "$INSTALL_DIR/venv/bin/astromeshctl" /usr/local/bin/astromeshctl

# Create _astromesh user if not exists
if ! dscl . -read /Users/_astromesh &>/dev/null; then
    # Find next available UID in the system range
    NEXT_UID=$(dscl . -list /Users UniqueID | awk '{print $2}' | sort -n | tail -1)
    NEXT_UID=$((NEXT_UID + 1))
    dscl . -create /Users/_astromesh
    dscl . -create /Users/_astromesh UserShell /usr/bin/false
    dscl . -create /Users/_astromesh UniqueID "$NEXT_UID"
    dscl . -create /Users/_astromesh PrimaryGroupID 20
    dscl . -create /Users/_astromesh NFSHomeDirectory /var/empty
    echo "Created _astromesh system user"
fi

# Install launchd plist if present
if [ -f "com.astromesh.daemon.plist" ]; then
    cp com.astromesh.daemon.plist /Library/LaunchDaemons/
    echo "Installed launchd plist"
fi

echo "Installation complete. Run 'astromeshctl init' to configure."
