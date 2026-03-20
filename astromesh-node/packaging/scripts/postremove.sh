#!/bin/bash
set -e

# Always reload systemd
systemctl daemon-reload

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
