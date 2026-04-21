# MongoDB compression load test (POC)

This folder contains a small Python load-test stub that:

- generates random documents (100+ fields)
- inserts ~200MB of synthetic data into MongoDB
- uses PyMongo wire compression (default: `snappy`)
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

Results are written to `metrics.output_path` (default `results.json`).

## Notes

- Init scripts run only when `../db/` is empty. This load test does *not* require re-init; it can drop just the target collection if configured.
- Compression here is **driver-to-server wire compression** (PyMongo `compressors=[...]`), not on-disk storage engine compression.

