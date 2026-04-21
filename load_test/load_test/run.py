import argparse
import json
import os
import random
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import psutil
import yaml
from bson import BSON
from pymongo import MongoClient, WriteConcern


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _rand_ascii(rng: random.Random, n: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(rng.choice(alphabet) for _ in range(n))


def generate_document(rng: random.Random, min_fields: int, blob_chars: int) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "ts_ms": _now_ms(),
        "blob": _rand_ascii(rng, blob_chars),
        "meta": {
            "session": _rand_ascii(rng, 16),
            "tags": [_rand_ascii(rng, 6) for _ in range(5)],
        },
    }

    for i in range(min_fields):
        key = f"field_{i:03d}"
        choice = i % 6
        if choice == 0:
            doc[key] = rng.randint(0, 1_000_000_000)
        elif choice == 1:
            doc[key] = rng.random()
        elif choice == 2:
            doc[key] = rng.choice([True, False])
        elif choice == 3:
            doc[key] = _rand_ascii(rng, 24)
        elif choice == 4:
            doc[key] = [rng.randint(0, 10_000) for _ in range(10)]
        else:
            doc[key] = {"k": _rand_ascii(rng, 8), "v": rng.randint(0, 10_000)}

    return doc


def estimate_bson_size(doc: Dict[str, Any]) -> int:
    return len(BSON.encode(doc))


@dataclass(frozen=True)
class Sample:
    t_ms: int
    cpu_percent: float
    rss_bytes: int


class MetricsSampler:
    def __init__(self, sample_interval_ms: int) -> None:
        self._interval_s = max(sample_interval_ms, 1) / 1000.0
        self._proc = psutil.Process(os.getpid())
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.samples: List[Sample] = []

    def start(self) -> None:
        self._proc.cpu_percent(interval=None)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            t_ms = _now_ms()
            cpu = self._proc.cpu_percent(interval=None)
            rss = self._proc.memory_info().rss
            self.samples.append(Sample(t_ms=t_ms, cpu_percent=cpu, rss_bytes=rss))
            time.sleep(self._interval_s)

    def summary(self) -> Dict[str, Any]:
        if not self.samples:
            return {"samples": 0}

        rss_values = [s.rss_bytes for s in self.samples]
        cpu_values = [s.cpu_percent for s in self.samples]
        return {
            "samples": len(self.samples),
            "rss_bytes_max": max(rss_values),
            "rss_bytes_min": min(rss_values),
            "rss_bytes_p95": _percentile(rss_values, 95),
            "cpu_percent_max": max(cpu_values),
            "cpu_percent_p95": _percentile(cpu_values, 95),
        }


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    k = (len(vs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(vs) - 1)
    if f == c:
        return float(vs[f])
    d0 = float(vs[f]) * (c - k)
    d1 = float(vs[c]) * (k - f)
    return d0 + d1


def load_config(path: str) -> Dict[str, Any]:
    # Allow running from repo root while pointing at config files in `load_test/`.
    # Example: `python -m load_test.clear_db --config config.yaml`
    # will fall back to `load_test/config.yaml` if needed.
    if not os.path.isabs(path) and not os.path.exists(path):
        load_test_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        fallback = os.path.join(load_test_dir, path)
        if os.path.exists(fallback):
            path = fallback

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _resolve_output_path(config_path: str, output_path: str) -> str:
    if os.path.isabs(output_path):
        return output_path
    return os.path.normpath(os.path.join(os.path.dirname(config_path), output_path))


def build_client(cfg: Dict[str, Any]) -> MongoClient:
    mcfg = cfg["mongodb"]
    compressors = mcfg.get("compressors") or None
    zlib_level = mcfg.get("zlib_compression_level")

    # POC behavior: treat ["snappy"] as "no compression".
    # This lets you keep the config default while effectively disabling compression.
    if isinstance(compressors, list) and compressors == ["snappy"]:
        compressors = None

    kwargs: Dict[str, Any] = {}
    if compressors is not None:
        kwargs["compressors"] = compressors
    if zlib_level is not None:
        kwargs["zlibCompressionLevel"] = zlib_level

    return MongoClient(mcfg["uri"], **kwargs)


def _make_collection(cfg: Dict[str, Any], client: MongoClient):
    mcfg = cfg["mongodb"]
    icfg = cfg["ingest"]
    w = icfg.get("w", 1)
    journal = icfg.get("journal", True)
    wc = WriteConcern(w=w, j=journal)
    return client.get_database(mcfg["database"]).get_collection(mcfg["collection"], write_concern=wc)


def _make_batches(
    *,
    rng: random.Random,
    target_bytes: int,
    min_fields: int,
    blob_chars: int,
    batch_size: int,
) -> Tuple[List[List[Dict[str, Any]]], int, int]:
    batches: List[List[Dict[str, Any]]] = []
    cur_batch: List[Dict[str, Any]] = []
    bytes_total = 0
    docs_total = 0

    while bytes_total < target_bytes:
        doc = generate_document(rng, min_fields=min_fields, blob_chars=blob_chars)
        bytes_total += estimate_bson_size(doc)
        docs_total += 1
        cur_batch.append(doc)
        if len(cur_batch) >= batch_size:
            batches.append(cur_batch)
            cur_batch = []

    if cur_batch:
        batches.append(cur_batch)

    return batches, docs_total, bytes_total


def _insert_worker(coll, batches: List[List[Dict[str, Any]]]) -> Tuple[int, int, int]:
    t0 = time.perf_counter_ns()
    docs = 0
    batches_done = 0
    for batch in batches:
        coll.insert_many(batch, ordered=False)
        docs += len(batch)
        batches_done += 1
    t1 = time.perf_counter_ns()
    return docs, batches_done, (t1 - t0) // 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Path to YAML config.")
    args = parser.parse_args()

    cfg = load_config(args.config)

    icfg = cfg["ingest"]
    dcfg = cfg["document"]
    mcfg = cfg["metrics"]

    threads = int(icfg.get("threads", 1))
    batch_size = int(icfg.get("batch_size", 1000))
    target_bytes = int(icfg.get("target_bytes", 209_715_200))

    seed = dcfg.get("seed")
    rng = random.Random(seed) if seed is not None else random.Random()

    batches, docs_total, bytes_total = _make_batches(
        rng=rng,
        target_bytes=target_bytes,
        min_fields=int(dcfg.get("min_fields", 100)),
        blob_chars=int(dcfg.get("blob_chars", 1024)),
        batch_size=batch_size,
    )

    client = build_client(cfg)
    coll = _make_collection(cfg, client)

    if bool(icfg.get("drop_collection_first", False)):
        coll.drop()

    # Split batches across workers (roughly evenly).
    worker_batches: List[List[List[Dict[str, Any]]]] = [[] for _ in range(max(threads, 1))]
    for idx, b in enumerate(batches):
        worker_batches[idx % len(worker_batches)].append(b)

    sampler = MetricsSampler(sample_interval_ms=int(mcfg.get("sample_interval_ms", 200)))
    sampler.start()

    start_ms = _now_ms()
    t0 = time.perf_counter_ns()

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(threads, 1)) as ex:
        futs = [ex.submit(_insert_worker, coll, wb) for wb in worker_batches if wb]
        for f in as_completed(futs):
            docs, batches_done, elapsed_ms = f.result()
            results.append(
                {"docs": docs, "batches": batches_done, "elapsed_ms": elapsed_ms}
            )

    t1 = time.perf_counter_ns()
    end_ms = _now_ms()
    sampler.stop()

    elapsed_ms_total = (t1 - t0) // 1_000_000
    docs_done = sum(r["docs"] for r in results)

    out = {
        "config_path": args.config,
        "mongodb": {
            "uri": cfg["mongodb"]["uri"],
            "database": cfg["mongodb"]["database"],
            "collection": cfg["mongodb"]["collection"],
            "compressors": cfg["mongodb"].get("compressors"),
        },
        "ingest": {
            "threads": threads,
            "batch_size": batch_size,
            "target_bytes_requested": target_bytes,
            "bytes_generated_estimate": bytes_total,
            "docs_generated": docs_total,
            "docs_inserted": docs_done,
        },
        "timing": {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "elapsed_ms": elapsed_ms_total,
            "docs_per_sec": (docs_done / (elapsed_ms_total / 1000.0)) if elapsed_ms_total else None,
            "mb_per_sec_estimate": ((bytes_total / (1024.0 * 1024.0)) / (elapsed_ms_total / 1000.0)) if elapsed_ms_total else None,
        },
        "workers": results,
        "process_metrics": sampler.summary(),
    }

    output_path = _resolve_output_path(
        args.config, str(mcfg.get("output_path", "results.json"))
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")

    print(json.dumps(out["timing"], indent=2, sort_keys=True))
    print(json.dumps(out["process_metrics"], indent=2, sort_keys=True))
    print(f"Wrote: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

