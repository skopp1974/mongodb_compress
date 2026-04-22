# MongoDB compression load test (POC)

This folder contains a small Python load-test stub that:

- generates random documents (100+ fields)
- inserts ~200MB of synthetic data into MongoDB
- runs a two-phase benchmark: compression, then no-compression, then compares
- records timing (millisecond precision) and CPU/memory usage & spikes during ingestion

## Setup

From `mongodb_compress/load_test`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the config:

```bash
cp config.example.yaml config.yaml
```

## Run

```bash
python -m load_test --config config.yaml
```

Results are written to `metrics.output_path` (default `results.json`) and contain:

- `results[0]`: compression run
- `results[1]`: no compression run
- `results[2]`: comparison deltas

## Understanding `results.json`

The output file has this shape:

- **`config_path`**: the config file path you passed on the command line.
- **`results`**: array of 3 objects:
  - **`results[0]`**: phase `"compression"` (uses `mongodb.compressors_for_compression_run`)
  - **`results[1]`**: phase `"no_compression"` (forces *no* wire compression)
  - **`results[2]`**: phase `"compare"` (delta between phase 1 and 2)

### Per-phase fields (`results[0]` and `results[1]`)

- **`phase`**: `"compression"` or `"no_compression"`.
- **`mongodb`**
  - **`uri` / `database` / `collection`**: where the data was inserted.
  - **`compressors_effective`**:
    - list (e.g. `["snappy"]`) means wire compression requested
    - `null` means no compression was used
- **`ingest`**
  - **`threads`**: number of concurrent ingest worker threads.
  - **`batch_size`**: documents per `insert_many`.
  - **`target_bytes_requested`**: configured target payload size (approx).
  - **`bytes_generated_estimate`**: estimated total BSON bytes of generated documents.
  - **`docs_generated`**: number of docs generated and inserted.
- **`timing`**
  - **`start_ms` / `end_ms`**: wall-clock timestamps in milliseconds.
  - **`elapsed_ms`**: total ingest duration in milliseconds.
  - **`docs_per_sec`**: throughput in documents/sec.
  - **`mb_per_sec_estimate`**: throughput based on `bytes_generated_estimate` (MiB/sec).
- **`process_metrics`** (Python process running the load test)
  - **`samples`**: number of CPU/RSS samples collected.
  - **`cpu_percent_max` / `cpu_percent_p95`**: CPU spikes (note: can exceed 100% on multi-core).
  - **`rss_bytes_min` / `rss_bytes_p95` / `rss_bytes_max`**: memory usage/spikes (RSS = *Resident Set Size*, i.e. physical RAM used by the Python process).
- **`mongo_footprint`** (MongoDB collection `collStats`)
  - **`count`**: documents in the collection.
  - **`size_bytes`**: logical size of the collection data.
  - **`storage_size_bytes`**: allocated storage size.
  - **`total_index_size_bytes`**: total index size.

Important: **wire compression (snappy/zlib/zstd) usually does not change `mongo_footprint`**,
because it affects network traffic, not the storage engine’s on-disk compression.

### Compare fields (`results[2]`)

`results[2].compare.<metric>` has:

- **`phase1`**: metric value from the `"compression"` phase
- **`phase2`**: metric value from the `"no_compression"` phase
- **`abs`**: \(phase2 - phase1\)
- **`pct`**: percent change relative to phase1, i.e. \((phase2 - phase1) / phase1 * 100\)

So:
- **negative** `abs` / `pct` means **no-compression was lower** than compression
- **positive** `abs` / `pct` means **no-compression was higher** than compression

For storage footprint, there are two helpful convenience fields:

- **`compare.mongo_storage_gain_bytes`**: \(storage(no_compression) - storage(compression)\)
  - positive means compression stored **less** on disk than no-compression
- **`compare.mongo_storage_gain_pct_vs_no_compression`**: the gain as a percent of the no-compression storage size

## Clear ingested data

Delete all documents from the configured collection:

```bash
python -m load_test.clear_db --config config.yaml
```

Or drop the collection entirely:

```bash
python -m load_test.clear_db --config config.yaml --drop
```

Or drop the entire database (most aggressive):

```bash
python -m load_test.clear_db --config config.yaml --drop-db
```

Or fully reclaim host disk space (runs `docker compose down`, deletes `../db/*`, then `docker compose up -d`):

```bash
python -m load_test.clear_db --config config.yaml --wipe-host-db-dir
```

This may prompt for your password via `sudo` (needed if Docker socket / db files are not owned by your user).

Note: even after dropping a collection/database, `du -hs ../db` may stay large because
WiredTiger may keep preallocated space in `.wt` files. If you want the host directory to
shrink back down, the simplest method in this repo is:

```bash
cd ../deployment
docker compose down
rm -rf ../db/*
docker compose up -d
```

## Notes

- Init scripts run only when `../db/` is empty. This load test does *not* require re-init; it can drop just the target collection if configured.
- Compression here is **driver-to-server wire compression** (PyMongo `compressors=[...]`), not on-disk storage engine compression.

