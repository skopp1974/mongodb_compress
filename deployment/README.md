# Deployment (Docker)

The full installation, runbook, results interpretation, and cleanup guide lives in the repo root:

- `../README.md`

This folder contains:

- `docker-compose.yml` (local MongoDB)
- `init_mongo_docker.sh` (clean reset: `docker compose down` + wipe `../db/*` + `up -d`)
- `install_doccker.sh` (install Docker on Debian/Ubuntu / typical Chromebook Linux)
- `initdb/` (optional first-boot init scripts when `../db/` is empty)
