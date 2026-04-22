# mongodb_compress

Local POC repo for benchmarking MongoDB ingestion and comparing:

- **network/payload compression** (PyMongo wire compression)
- **on-disk storage compression** (WiredTiger `block_compressor` per collection)

Data is persisted on the host at `mongodb_compress/db/` (bind-mounted into Docker).

## Prereqs

- Docker + Docker Compose plugin (`docker compose`)
- Python 3.9+ (for `load_test/`)

## Install Docker (one time)

If `docker` is not installed:

```bash
cd ~/repos/mongodb_compress/deployment
./install_doccker.sh
```

Then apply the docker group in your shell:

```bash
newgrp docker
```

If that doesn’t work, open a new terminal (or log out/in).

## Start / reset MongoDB (recommended)

This script is the cleanest way to avoid carrying stale WiredTiger files between runs:

```bash
~/repos/mongodb_compress/deployment/init_mongo_docker.sh
```

It runs:

```bash
cd ~/repos/mongodb_compress/deployment
sudo docker compose down
sudo rm -rf ../db/*
sudo docker compose up -d
```

Notes:

- It may prompt for `sudo` (docker socket / file permissions on Chromebook Linux).
- On first startup with an **empty** `db/`, MongoDB init scripts create `compress_poc` and a tiny `init` collection (see `deployment/initdb/`).

### Manual Docker commands (equivalent)

From `mongodb_compress/deployment`:

```bash
docker compose up -d
```

MongoDB is reachable at `mongodb://localhost:27017` (unless you enable auth; see below).

### Optional: enable auth (local)

```bash
cd ~/repos/mongodb_compress/deployment
cp .env.example .env
# edit .env and set a strong password
docker compose up -d
```

Connect:

```bash
mongosh "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/admin"
```

### Logs / stop

```bash
cd ~/repos/mongodb_compress/deployment
docker compose logs -f mongodb
docker compose down
```

## Run the load test

One-time Python setup (repo root venv recommended):

```bash
cd ~/repos/mongodb_compress
python3 -m venv .venv
source .venv/bin/activate
pip install -r load_test/requirements.txt
cp -n load_test/config.example.yaml load_test/config.yaml
```

Run (from repo root, which is how the paths were written in this repo’s docs):

```bash
cd ~/repos/mongodb_compress
source .venv/bin/activate
python -m load_test --config load_test/config.yaml
```

This writes `load_test/results.json` (gitignored).

## `load_test/config.yaml` (what the knobs mean)

The benchmark is two-phase when `ingest.run_comparison: true`:

1) **“compression” phase** (phase name in results: `"compression"`)  
2) **“no compression” phase** (phase name in results: `"no_compression"`)

### On-disk / storage settings (WiredTiger)

These affect **MongoDB storage footprint** (what you care about for “disk compression”):

- `mongodb.storage_block_compressor_for_compression_run`
- `mongodb.storage_block_compressor_for_no_compression_run`
- `mongodb.recreate_collection_each_phase: true` (required so the compressor is applied at collection creation)

Typical values: `"zstd"`, `"snappy"`, `"zlib"`, `"none"`.

### Network / wire settings (PyMongo)

These affect **client↔server network payload compression** (generally not the same as on-disk storage size):

- `mongodb.network_payload_compressors_for_compression_run` (e.g. `["snappy"]`, `["zlib"]`, `["zstd"]`)
- `mongodb.network_payload_compressors_for_no_compression_run` (usually `[]`)

`mongodb.zlib_compression_level` only matters when you use `["zlib"]` for wire compression.

## Understanding `load_test/results.json`

`results.json` is shaped like:

- `config_path`
- `results`: an array with 3 items when `ingest.run_comparison: true`
  - `results[0]`: phase `"compression"`
  - `results[1]`: phase `"no_compression"`
  - `results[2]`: phase `"compare"`

### `compressors_effective` vs `storage_block_compressor_effective`

Inside each per-phase object (e.g. `results[0].mongodb`):

- `compressors_effective` is the **PyMongo wire compression** list (or `null` if disabled).
- `storage_block_compressor_effective` (when `recreate_collection_each_phase: true`) is the **WiredTiger** compressor for that phase’s recreated collection.

### `process_metrics` (Python process)

This measures the **load test client process** (not the MongoDB server container):

- **RSS** = *Resident Set Size* = physical RAM used by the Python process.
- **p95** = 95th percentile of samples taken during the ingest window.

### Compare section (`results[2]`)

For most metrics, each compare entry is:

- `phase1` = value from the `"compression"` run
- `phase2` = value from the `"no_compression"` run
- `abs` = `phase2 - phase1`
- `pct` = \((phase2 - phase1) / phase1 * 100\)

Storage helpers:

- `compare.mongo_storage_gain_bytes` = `storage_size_bytes(no_compression) - storage_size_bytes(compression)`  
  - positive means the compression run used **less disk** than the no-compression run
- `compare.mongo_storage_gain_pct_vs_no_compression` expresses that gain as a percent of the no-compression storage size

## Cleanup

### Clear Mongo data inside Mongo (logical delete)

```bash
cd ~/repos/mongodb_compress
source .venv/bin/activate
python -m load_test.clear_db --config load_test/config.yaml --drop-db
```

This removes databases/collections, but the host `db/` directory can still look large (WiredTiger preallocation/reuse).

### Reclaim host disk space (fully wipe `db/`)

```bash
cd ~/repos/mongodb_compress
source .venv/bin/activate
python -m load_test.clear_db --config load_test/config.yaml --wipe-host-db-dir
```

## Where other docs live

- `deployment/README.md` and `load_test/README.md` are now short pointers; this file is the single “wiki” for the repo.
