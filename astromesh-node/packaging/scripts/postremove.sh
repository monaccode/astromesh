#!/bin/bash
set -e

# Always reload systemd (when there is one: containers and chroots have no systemctl)
if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload
fi

# On purge: remove all data and the system user
if [ "$1" = "purge" ]; then
    rm -rf /var/lib/astromesh
    rm -rf /var/log/astromesh
    rm -rf /opt/astromesh

    if getent passwd astromesh >/dev/null 2>&1; then
        userdel astromesh
    fi

    if getent group astromesh >/dev/null 2>&1; then
        groupdel astromesh
    fi
fi
