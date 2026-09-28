#!/bin/bash
# Builds dist/astromesh-node_<version>_amd64.deb. Needs a writable /opt/astromesh — see
# build-venv.sh. Run from anywhere; it cds to astromesh-node/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
export VERSION
echo "==> Building astromesh-node ${VERSION} .deb package"

[ -x /opt/astromesh/venv/bin/astromeshd ] && [ "${REUSE_VENV:-0}" = "1" ] || bash packaging/build-venv.sh

mkdir -p dist
VERSION="${VERSION}" nfpm package --config packaging/nfpm.yaml --packager deb --target dist/

DEB_FILE="dist/astromesh-node_${VERSION}_amd64.deb"
if [ -f "$DEB_FILE" ]; then
    echo "==> Success: $DEB_FILE"
    dpkg-deb --info "$DEB_FILE" 2>/dev/null || true
else
    echo "==> ERROR: Expected $DEB_FILE not found"
    ls -la dist/
    exit 1
fi
