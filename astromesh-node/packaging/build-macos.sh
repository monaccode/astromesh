#!/usr/bin/env bash
# Builds dist/astromesh-node-<version>-macos-<arm64|x86_64>.tar.gz: a standalone CPython and a venv built on
# it, both AT THEIR FINAL PATH (/usr/local/opt/astromesh), plus install.sh and the launchd
# plist. A venv is not relocatable: until node 0.1.8 it was built in staging/ with the
# runner's python.org Python and every tarball failed with "bad interpreter".
#
# Needs a writable /usr/local/opt/astromesh (CI pre-creates it). Architecture follows the
# build machine; CI builds one tarball on Apple silicon and one on Intel.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)
PREFIX="${ASTROMESH_PREFIX:-/usr/local/opt/astromesh}"
echo "==> Building astromesh-node ${VERSION} for macOS into ${PREFIX}"

PBS_RELEASE="20260924"
PY_VERSION="3.12.14"
case "$(uname -m)" in
    arm64)  PY_TRIPLE="aarch64-apple-darwin"; PY_SHA256="c2edb321cd32ec2b170df208db0446dccc4398db602ca27cf2079098fb1f7d9d" ;;
    x86_64) PY_TRIPLE="x86_64-apple-darwin";  PY_SHA256="7ea9761b9069c10b9a20531d568645849d604c59e9c7f11f6659f1e1790c968e" ;;
    *) echo "==> ERROR: unsupported arch $(uname -m)"; exit 1 ;;
esac
PY_ASSET="cpython-${PY_VERSION}+${PBS_RELEASE}-${PY_TRIPLE}-install_only_stripped.tar.gz"

rm -rf "${PREFIX}/python" "${PREFIX}/venv"
mkdir -p "${PREFIX}" dist
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
curl -fsSL "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${PY_ASSET}" -o "${tmp}/python.tar.gz"
echo "${PY_SHA256}  ${tmp}/python.tar.gz" | shasum -a 256 -c -
tar -xzf "${tmp}/python.tar.gz" -C "${PREFIX}"   # unpacks to python/

"${PREFIX}/python/bin/python3" -m venv "${PREFIX}/venv"
"${PREFIX}/venv/bin/pip" install --upgrade pip --quiet
"${PREFIX}/venv/bin/pip" install "../[observability]" "./" --quiet

find "${PREFIX}/venv" "${PREFIX}/python" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
rm -rf "${PREFIX}"/python/lib/python3.*/{tkinter,idlelib,turtledemo,test} \
    "${PREFIX}"/python/lib/{tcl,tk,itcl,thread}* "${PREFIX}"/python/lib/lib{tcl,tk}*

bad=0
for f in "${PREFIX}/venv/bin/"*; do
    [ -f "${f}" ] && [ ! -L "${f}" ] || continue
    first=$(head -n1 "${f}" 2>/dev/null || true)
    case "${first}" in
        "#!${PREFIX}/venv/bin/python"*) ;;
        "#!"*python*) echo "==> ERROR: ${f} has shebang ${first}"; bad=1 ;;
    esac
done
[ "${bad}" = "0" ] || exit 1
"${PREFIX}/venv/bin/python" -c "import astromesh.api.main, astromesh_node; print('==> venv OK', astromesh_node.__version__)"

OUT="dist/astromesh-node-${VERSION}-macos-$(uname -m).tar.gz"
tar czf "${OUT}" \
    -C "${PREFIX}" python venv \
    -C "${PWD}/packaging/scripts" install.sh \
    -C "${PWD}/packaging/launchd" com.astromesh.daemon.plist
echo "==> Built ${OUT}"
