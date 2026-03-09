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

# Reload systemd and enable service (do NOT start — user must configure first)
systemctl daemon-reload
systemctl enable astromeshd.service
