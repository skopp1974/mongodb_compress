#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}/deployment"

sudo docker compose down
sudo rm -rf ../db/*
sudo docker compose up -d

cat <<'EOF'

MongoDB is up.

Next steps (one-time Python setup):
  cd ~/repos/mongodb_compress
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r load_test/requirements.txt

Run the load test:
  cd ~/repos/mongodb_compress
  source .venv/bin/activate
  cp -n load_test/config.example.yaml load_test/config.yaml
  python -m load_test --config config.yaml

EOF

