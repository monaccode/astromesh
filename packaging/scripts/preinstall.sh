#!/bin/bash
set -e

# Create astromesh system user and group (idempotent)
if ! getent group astromesh >/dev/null 2>&1; then
    groupadd --system astromesh
fi

if ! getent passwd astromesh >/dev/null 2>&1; then
    useradd --system \
        --gid astromesh \
        --home-dir /var/lib/astromesh \
        --shell /usr/sbin/nologin \
        --no-create-home \
        astromesh
fi
