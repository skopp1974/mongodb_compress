#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}/deployment"

sudo docker compose down
sudo rm -rf ../db/*
sudo docker compose up -d

cat <<'EOF'

MongoDB is up.

Run the load test:
  cd ~/repos/mongodb_compress
  source .venv/bin/activate   # if you use the repo-root venv
  python -m load_test --config config.yaml

EOF

