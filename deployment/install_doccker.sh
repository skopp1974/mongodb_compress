#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  echo "Please run as a normal user (no sudo). This script will prompt for sudo when needed." >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Cannot detect OS (/etc/os-release missing)." >&2
  exit 1
fi

. /etc/os-release

case "${ID:-}" in
  debian|ubuntu)
    ;;
  *)
    echo "Unsupported distro: ${ID:-unknown}. This script supports Debian/Ubuntu (common in Chromebook Linux)." >&2
    exit 1
    ;;
esac

sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL "https://download.docker.com/linux/${ID}/gpg" | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

ARCH="$(dpkg --print-architecture)"
CODENAME="${VERSION_CODENAME:-$(. /etc/os-release && echo "${VERSION_CODENAME}")}"

echo \
  "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${CODENAME} stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

cat <<'EOF'
Docker installed.

Next steps:
  1) Close this terminal and open a new one (or log out/in) so the docker group applies.
  2) Verify:
       docker version
       docker compose version
  3) Start MongoDB:
       cd ~/repos/mongodb_compress/deployment
       docker compose up -d
EOF

