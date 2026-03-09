#!/bin/bash
set -e

# Stop and disable the service
if systemctl is-active --quiet astromeshd.service 2>/dev/null; then
    systemctl stop astromeshd.service
fi

if systemctl is-enabled --quiet astromeshd.service 2>/dev/null; then
    systemctl disable astromeshd.service
fi
