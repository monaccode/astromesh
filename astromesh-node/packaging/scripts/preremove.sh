#!/bin/bash
set -e

# Stop and disable only on a real removal. On an upgrade the OLD package's prerm/%preun
# runs too — after the new one's postinst/%post on rpm — and disabling here left an
# upgraded node stopped and disabled. deb: prerm remove|upgrade|...; rpm: %preun $1 is the
# number of instances left (0 = erase, 1 = upgrade).
case "$1" in
    remove|purge|0) ;;
    *) exit 0 ;;
esac

if systemctl is-active --quiet astromeshd.service 2>/dev/null; then
    systemctl stop astromeshd.service
fi

if systemctl is-enabled --quiet astromeshd.service 2>/dev/null; then
    systemctl disable astromeshd.service
fi
