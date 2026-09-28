#!/usr/bin/env bash
# Builds dist/astromesh-node-<version>-1.x86_64.rpm from the same /opt/astromesh runtime as
# the .deb (see build-venv.sh). Run from anywhere; it cds to astromesh-node/.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
echo "==> Building astromesh-node ${VERSION} .rpm package"

[ -x /opt/astromesh/venv/bin/astromeshd ] && [ "${REUSE_VENV:-0}" = "1" ] || bash packaging/build-venv.sh

mkdir -p dist
VERSION="${VERSION}" nfpm package --config packaging/nfpm.yaml --packager rpm --target dist/
echo "==> Built $(ls dist/*.rpm)"
