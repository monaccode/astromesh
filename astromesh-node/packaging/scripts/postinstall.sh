#!/bin/bash
set -e

# Create runtime directories
mkdir -p /var/lib/astromesh/{models,memory,data}
mkdir -p /var/log/astromesh/audit

# Set ownership and permissions
chown -R astromesh:astromesh /var/lib/astromesh
chown -R astromesh:astromesh /var/log/astromesh
chmod 750 /var/lib/astromesh
chmod 750 /var/log/astromesh

# Ensure config directory ownership
chown -R root:astromesh /etc/astromesh
chmod 750 /etc/astromesh
chmod 640 /etc/astromesh/*.yaml
chmod 750 /etc/astromesh/agents /etc/astromesh/profiles
chmod 640 /etc/astromesh/agents/* /etc/astromesh/profiles/*

# Containers and build chroots have no systemctl; the files are in place either way, and a
# failing postinst would leave the package half-configured.
if ! command -v systemctl >/dev/null 2>&1; then
    echo "  systemctl not found: skipping service setup. Run 'astromeshctl init' to configure."
    exit 0
fi

systemctl daemon-reload

# Fresh install vs upgrade. deb: postinst configure <old-version> (empty on a fresh install);
# rpm: %post $1 is the number of instances after the transaction (1 = fresh, 2+ = upgrade).
if [ "$1" = "configure" ] && [ -n "$2" ] || [ "$1" -ge 2 ] 2>/dev/null; then
    # Upgrade: keep whatever enabled state the admin chose, and pick up the new code if it
    # was running.
    systemctl try-restart astromeshd.service
else
    # Fresh install: enable, but do NOT start — the node must be configured first.
    systemctl enable astromeshd.service
    echo ""
    echo "  Run 'astromeshctl init' to configure this node."
    echo ""
fi
