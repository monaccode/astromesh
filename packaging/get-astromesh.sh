#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://monaccode.github.io/astromech-platform"
REQUIRED_PYTHON="3.12"

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { printf "${CYAN}[info]${NC}  %s\n" "$*"; }
success() { printf "${GREEN}[ok]${NC}    %s\n" "$*"; }
warn()    { printf "${YELLOW}[warn]${NC}  %s\n" "$*"; }
error()   { printf "${RED}[error]${NC} %s\n" "$*" >&2; }

# ---------------------------------------------------------------------------
# print_banner — Astromesh ASCII art
# ---------------------------------------------------------------------------
print_banner() {
    printf "${CYAN}${BOLD}"
    cat <<'BANNER'

     _         _                                _
    / \   ___ | |_ _ __ ___  _ __ ___   ___  __| |__
   / _ \ / __|| __| '__/ _ \| '_ ` _ \ / _ \/ __| '_ \
  / ___ \\__ \| |_| | | (_) | | | | | |  __/\__ \ | | |
 /_/   \_\___/ \__|_|  \___/|_| |_| |_|\___||___/_| |_|

BANNER
    printf "${NC}\n"
    info "Astromesh Platform Installer"
    echo ""
}

# ---------------------------------------------------------------------------
# detect_os — Parse /etc/os-release to determine distro family
# ---------------------------------------------------------------------------
detect_os() {
    if [[ ! -f /etc/os-release ]]; then
        OS_FAMILY="unknown"
        return
    fi

    # shellcheck source=/dev/null
    . /etc/os-release

    if [[ "${ID_LIKE:-}" == *"debian"* ]] || [[ "${ID:-}" == "debian" ]] || [[ "${ID:-}" == "ubuntu" ]]; then
        OS_FAMILY="debian"
    else
        OS_FAMILY="unknown"
    fi
}

# ---------------------------------------------------------------------------
# detect_arch — Map uname -m to Debian arch names
# ---------------------------------------------------------------------------
detect_arch() {
    local machine
    machine="$(uname -m)"

    case "${machine}" in
        x86_64)  ARCH="amd64" ;;
        aarch64) ARCH="arm64" ;;
        armv7l)  ARCH="armhf" ;;
        *)
            error "Unsupported architecture: ${machine}"
            exit 1
            ;;
    esac

    info "Detected architecture: ${machine} -> ${ARCH}"
}

# ---------------------------------------------------------------------------
# check_python — Verify python3 >= REQUIRED_PYTHON is available
# ---------------------------------------------------------------------------
check_python() {
    if ! command -v python3 &>/dev/null; then
        warn "python3 not found. The package will attempt to install it as a dependency."
        return
    fi

    local version
    version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

    local major minor req_major req_minor
    IFS='.' read -r major minor <<< "${version}"
    IFS='.' read -r req_major req_minor <<< "${REQUIRED_PYTHON}"

    if (( major > req_major )) || { (( major == req_major )) && (( minor >= req_minor )); }; then
        success "Python ${version} detected (>= ${REQUIRED_PYTHON})"
    else
        warn "Python ${version} detected, but >= ${REQUIRED_PYTHON} is required."
        warn "The package will attempt to install a compatible version."
    fi
}

# ---------------------------------------------------------------------------
# check_root — Ensure we can run privileged commands
# ---------------------------------------------------------------------------
check_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        SUDO=""
    elif command -v sudo &>/dev/null; then
        info "Root privileges required. You may be prompted for your password."
        SUDO="sudo"
    else
        error "This script must be run as root or with sudo available."
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# install_apt_repo — Add GPG key and APT sources list entry (idempotent)
# ---------------------------------------------------------------------------
install_apt_repo() {
    local keyring="/usr/share/keyrings/astromesh-archive-keyring.gpg"
    local sources_list="/etc/apt/sources.list.d/astromesh.list"

    # Skip if already configured
    if [[ -f "${sources_list}" ]] && [[ -f "${keyring}" ]]; then
        success "APT repository already configured — skipping."
        return
    fi

    info "Adding Astromesh APT repository..."

    # Install prerequisites
    ${SUDO} apt-get update -qq
    ${SUDO} apt-get install -y -qq curl gnupg ca-certificates >/dev/null

    # Import GPG key
    curl -fsSL "${REPO_URL}/gpg" | ${SUDO} gpg --dearmor -o "${keyring}"
    success "GPG key installed."

    # Add sources list entry
    echo "deb [signed-by=${keyring} arch=${ARCH}] ${REPO_URL}/apt stable main" \
        | ${SUDO} tee "${sources_list}" >/dev/null
    success "APT source added."
}

# ---------------------------------------------------------------------------
# install_package — Install the astromesh package via apt
# ---------------------------------------------------------------------------
install_package() {
    info "Installing astromesh package..."
    ${SUDO} apt-get update -qq
    ${SUDO} apt-get install -y astromesh
    success "Astromesh installed successfully!"
}

# ---------------------------------------------------------------------------
# suggest_docker — Print Docker alternative for non-Debian systems
# ---------------------------------------------------------------------------
suggest_docker() {
    echo ""
    warn "Astromesh APT packages are only available for Debian/Ubuntu systems."
    echo ""
    info "You can run Astromesh using Docker instead:"
    echo ""
    printf "  ${BOLD}curl -fsSL ${REPO_URL}/docker-compose.yml -o docker-compose.yml${NC}\n"
    printf "  ${BOLD}docker compose up -d${NC}\n"
    echo ""
    info "Or install from source with uv:"
    echo ""
    printf "  ${BOLD}pip install uv${NC}\n"
    printf "  ${BOLD}git clone https://github.com/monaccode/astromech-platform.git${NC}\n"
    printf "  ${BOLD}cd astromech-platform && uv sync --extra all${NC}\n"
    echo ""
}

# ---------------------------------------------------------------------------
# main — Orchestrate the installation
# ---------------------------------------------------------------------------
main() {
    print_banner

    detect_os
    detect_arch

    if [[ "${OS_FAMILY}" != "debian" ]]; then
        suggest_docker
        exit 0
    fi

    check_python
    check_root
    install_apt_repo
    install_package

    echo ""
    success "Installation complete! Starting initial setup..."
    echo ""

    # Hand off to the init wizard
    exec astromeshctl init
}

main "$@"
