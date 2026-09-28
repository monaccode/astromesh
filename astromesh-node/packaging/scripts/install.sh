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

# Copy the bundled CPython and the venv built on it. Both were built at exactly these paths,
# so they must land there. Remove the old ones first: `cp -R venv <existing dir>` nests the
# new venv inside the old one.
mkdir -p "$INSTALL_DIR"
for part in python venv; do
    if [ ! -d "$part" ]; then
        echo "Missing $part/ — run install.sh from the extracted tarball"; exit 1
    fi
    rm -rf "${INSTALL_DIR:?}/$part"
    cp -R "$part" "$INSTALL_DIR/$part"
done
echo "Installed runtime to $INSTALL_DIR"

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
