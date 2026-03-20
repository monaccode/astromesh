#!/usr/bin/env bash
set -euo pipefail

VERSION=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
echo "Building astromesh-node ${VERSION} for macOS..."

STAGING="staging/macos"
rm -rf "$STAGING"
mkdir -p "$STAGING" dist

python3 -m venv "$STAGING/venv"
"$STAGING/venv/bin/pip" install --quiet ../ ./

cp packaging/launchd/com.astromesh.daemon.plist "$STAGING/" 2>/dev/null || true
cp packaging/scripts/install.sh "$STAGING/"

tar czf "dist/astromesh-node-${VERSION}-macos.tar.gz" -C "$STAGING" .
echo "Built dist/astromesh-node-${VERSION}-macos.tar.gz"
