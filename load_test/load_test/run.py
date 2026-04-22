import argparse
import json
import os
import random
import sys
import string
import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import psutil
import yaml
from bson import BSON
from pymongo import MongoClient, WriteConcern
from pymongo.errors import ServerSelectionTimeoutError


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

def _default_report_path(config_path: str) -> str:
    reports_dir = os.path.join(os.path.dirname(config_path), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return os.path.join(reports_dir, f"reports_{ts}.json")


def _normalize_compressors(
    compressors: Any,
) -> Optional[List[str]]:
    if compressors is None:
        return None
    if compressors == []:
        return None
    if isinstance(compressors, str):
        compressors = [compressors]
    if not isinstance(compressors, list):
        return None
    compressors = [str(x) for x in compressors]
    return compressors


def build_client(
    cfg: Dict[str, Any],
    *,
    compressors_override: Optional[List[str]] = None,
) -> MongoClient:
    mcfg = cfg["mongodb"]
    compressors = (
        compressors_override
        if compressors_override is not None
        else mcfg.get("network_payload_compressors_for_compression_run")
    )
    zlib_level = mcfg.get("zlib_compression_level")

    compressors = _normalize_compressors(compressors)

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


def _recreate_collection_with_block_compressor(
    cfg: Dict[str, Any],
    client: MongoClient,
    *,
    block_compressor: Optional[str],
) -> None:
    mcfg = cfg["mongodb"]
    db = client.get_database(mcfg["database"])
    name = mcfg["collection"]

    try:
        db.drop_collection(name)
    except Exception:
        pass

    if not block_compressor:
        db.create_collection(name)
        return

    # WiredTiger configString expects values like: block_compressor=zstd|snappy|zlib|none
    db.create_collection(
        name,
        storageEngine={
            "wiredTiger": {"configString": f"block_compressor={block_compressor}"}
        },
    )


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


@dataclass
class ProgressState:
    total_batches: int
    total_docs: int
    total_bytes_est: int
    lock: threading.Lock
    done_batches: int = 0
    done_docs: int = 0
    done_bytes_est: int = 0


class ProgressPrinter:
    def __init__(self, state: ProgressState, interval_s: float = 1.0) -> None:
        self._state = state
        self._interval_s = max(interval_s, 0.2)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        sys.stderr.write("\n")
        sys.stderr.flush()

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._state.lock:
                b = self._state.done_batches
                d = self._state.done_docs
                by = self._state.done_bytes_est
                tb = self._state.total_batches
                td = self._state.total_docs
                tby = self._state.total_bytes_est

            pct = (100.0 * b / tb) if tb else 0.0
            mb = by / (1024.0 * 1024.0)
            tmb = tby / (1024.0 * 1024.0)
            sys.stderr.write(
                f"\rProgress: {pct:6.2f}%  batches {b}/{tb}  docs {d}/{td}  est {mb:,.1f}/{tmb:,.1f} MiB"
            )
            sys.stderr.flush()
            time.sleep(self._interval_s)


def _insert_worker_with_progress(
    coll, batches: List[List[Dict[str, Any]]], progress: ProgressState
) -> Tuple[int, int, int]:
    t0 = time.perf_counter_ns()
    docs_flush = 0
    bytes_flush = 0
    batches_done = 0

    for batch in batches:
        coll.insert_many(batch, ordered=False)
        batches_done += 1
        docs_flush += len(batch)
        bytes_flush += sum(estimate_bson_size(doc) for doc in batch)

        if batches_done % 5 == 0:
            with progress.lock:
                progress.done_batches += 5
                progress.done_docs += docs_flush
                progress.done_bytes_est += bytes_flush
            docs_flush = 0
            bytes_flush = 0

    remainder = batches_done % 5
    if remainder or docs_flush or bytes_flush:
        with progress.lock:
            progress.done_batches += remainder
            progress.done_docs += docs_flush
            progress.done_bytes_est += bytes_flush

    t1 = time.perf_counter_ns()
    return docs_flush, batches_done, (t1 - t0) // 1_000_000


def _run_phase(
    *,
    cfg: Dict[str, Any],
    batches: List[List[Dict[str, Any]]],
    docs_total: int,
    bytes_total_est: int,
    threads: int,
    phase_name: str,
    compressors_override: Optional[List[str]],
) -> Dict[str, Any]:
    icfg = cfg["ingest"]
    mcfg = cfg["metrics"]

    client = build_client(
        cfg,
        compressors_override=compressors_override,
    )

    mdb_cfg = cfg.get("mongodb", {})
    recreate_each_phase = bool(mdb_cfg.get("recreate_collection_each_phase", False))
    if recreate_each_phase:
        _recreate_collection_with_block_compressor(
            cfg,
            client,
            block_compressor=mdb_cfg.get(
                "storage_block_compressor_for_compression_run"
                if phase_name == "compression"
                else "storage_block_compressor_for_no_compression_run"
            ),
        )

    coll = _make_collection(cfg, client)

    worker_batches: List[List[List[Dict[str, Any]]]] = [[] for _ in range(max(threads, 1))]
    for idx, b in enumerate(batches):
        worker_batches[idx % len(worker_batches)].append(b)

    progress = ProgressState(
        total_batches=len(batches),
        total_docs=docs_total,
        total_bytes_est=bytes_total_est,
        lock=threading.Lock(),
    )
    progress_printer = ProgressPrinter(progress, interval_s=1.0)

    sampler = MetricsSampler(sample_interval_ms=int(mcfg.get("sample_interval_ms", 200)))
    sampler.start()
    progress_printer.start()

    start_ms = _now_ms()
    t0 = time.perf_counter_ns()

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(threads, 1)) as ex:
        futs = [
            ex.submit(_insert_worker_with_progress, coll, wb, progress)
            for wb in worker_batches
            if wb
        ]
        for f in as_completed(futs):
            docs, batches_done, elapsed_ms = f.result()
            results.append({"docs": docs, "batches": batches_done, "elapsed_ms": elapsed_ms})

    t1 = time.perf_counter_ns()
    end_ms = _now_ms()
    progress_printer.stop()
    sampler.stop()

    elapsed_ms_total = (t1 - t0) // 1_000_000

    footprint = _get_collection_footprint_bytes(coll)

    return {
        "phase": phase_name,
        "mongodb": {
            "uri": cfg["mongodb"]["uri"],
            "database": cfg["mongodb"]["database"],
            "collection": cfg["mongodb"]["collection"],
            "compressors_effective": compressors_override,
            "storage_block_compressor_effective": (
                mdb_cfg.get("storage_block_compressor_for_compression_run")
                if phase_name == "compression"
                else mdb_cfg.get("storage_block_compressor_for_no_compression_run")
            )
            if recreate_each_phase
            else None,
        },
        "mongo_footprint": footprint,
        "ingest": {
            "threads": threads,
            "batch_size": int(icfg.get("batch_size", 1000)),
            "target_bytes_requested": int(icfg.get("target_bytes", 209_715_200)),
            "bytes_generated_estimate": bytes_total_est,
            "docs_generated": docs_total,
        },
        "timing": {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "elapsed_ms": elapsed_ms_total,
            "docs_per_sec": (docs_total / (elapsed_ms_total / 1000.0)) if elapsed_ms_total else None,
            "mb_per_sec_estimate": ((bytes_total_est / (1024.0 * 1024.0)) / (elapsed_ms_total / 1000.0)) if elapsed_ms_total else None,
        },
        "workers": results,
        "process_metrics": sampler.summary(),
    }


def _get_collection_footprint_bytes(coll) -> Dict[str, Optional[int]]:
    # MongoDB footprint is about storage engine data/index size on disk.
    # Driver wire-compression (snappy/zlib/zstd) generally does NOT change this number.
    # WiredTiger block compression DOES change it, but only if the collection is created that way.
    try:
        stats = coll.database.command("collStats", coll.name)
    except Exception:
        return {
            "count": None,
            "size_bytes": None,
            "storage_size_bytes": None,
            "total_index_size_bytes": None,
        }

    total_index_size = stats.get("totalIndexSize")
    return {
        "count": int(stats["count"]) if "count" in stats else None,
        "size_bytes": int(stats["size"]) if "size" in stats else None,
        "storage_size_bytes": int(stats["storageSize"]) if "storageSize" in stats else None,
        "total_index_size_bytes": int(total_index_size) if total_index_size is not None else None,
    }


def _compare_results(phase1: Dict[str, Any], phase2: Dict[str, Any]) -> Dict[str, Any]:
    def _get(obj: Dict[str, Any], path: List[str]) -> Optional[float]:
        cur: Any = obj
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return None
            cur = cur[p]
        if cur is None:
            return None
        try:
            return float(cur)
        except Exception:
            return None

    def _delta(a: Optional[float], b: Optional[float]) -> Dict[str, Optional[float]]:
        if a is None or b is None:
            return {"phase1": a, "phase2": b, "abs": None, "pct": None}
        abs_d = b - a
        pct = (abs_d / a) * 100.0 if a != 0 else None
        return {"phase1": a, "phase2": b, "abs": abs_d, "pct": pct}

    storage_phase1 = _get(phase1, ["mongo_footprint", "storage_size_bytes"])
    storage_phase2 = _get(phase2, ["mongo_footprint", "storage_size_bytes"])
    storage_gain_bytes = (storage_phase2 - storage_phase1) if (storage_phase1 is not None and storage_phase2 is not None) else None
    storage_gain_pct_vs_no_compression = (
        (storage_gain_bytes / storage_phase2) * 100.0
        if (storage_gain_bytes is not None and storage_phase2 not in (None, 0))
        else None
    )

    return {
        "phase": "compare",
        "compare": {
            "elapsed_ms": _delta(
                _get(phase1, ["timing", "elapsed_ms"]),
                _get(phase2, ["timing", "elapsed_ms"]),
            ),
            "docs_per_sec": _delta(
                _get(phase1, ["timing", "docs_per_sec"]),
                _get(phase2, ["timing", "docs_per_sec"]),
            ),
            "mb_per_sec_estimate": _delta(
                _get(phase1, ["timing", "mb_per_sec_estimate"]),
                _get(phase2, ["timing", "mb_per_sec_estimate"]),
            ),
            "cpu_percent_p95": _delta(
                _get(phase1, ["process_metrics", "cpu_percent_p95"]),
                _get(phase2, ["process_metrics", "cpu_percent_p95"]),
            ),
            "cpu_percent_max": _delta(
                _get(phase1, ["process_metrics", "cpu_percent_max"]),
                _get(phase2, ["process_metrics", "cpu_percent_max"]),
            ),
            "rss_bytes_p95": _delta(
                _get(phase1, ["process_metrics", "rss_bytes_p95"]),
                _get(phase2, ["process_metrics", "rss_bytes_p95"]),
            ),
            "rss_bytes_max": _delta(
                _get(phase1, ["process_metrics", "rss_bytes_max"]),
                _get(phase2, ["process_metrics", "rss_bytes_max"]),
            ),
            "mongo_storage_size_bytes": _delta(
                _get(phase1, ["mongo_footprint", "storage_size_bytes"]),
                _get(phase2, ["mongo_footprint", "storage_size_bytes"]),
            ),
            "mongo_total_index_size_bytes": _delta(
                _get(phase1, ["mongo_footprint", "total_index_size_bytes"]),
                _get(phase2, ["mongo_footprint", "total_index_size_bytes"]),
            ),
            # Convenience: positive means "compression used less disk than no compression".
            "mongo_storage_gain_bytes": storage_gain_bytes,
            "mongo_storage_gain_pct_vs_no_compression": storage_gain_pct_vs_no_compression,
        },
    }

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
    run_comparison = bool(icfg.get("run_comparison", True))

    seed = dcfg.get("seed")
    rng = random.Random(seed) if seed is not None else random.Random()

    batches, docs_total, bytes_total = _make_batches(
        rng=rng,
        target_bytes=target_bytes,
        min_fields=int(dcfg.get("min_fields", 100)),
        blob_chars=int(dcfg.get("blob_chars", 1024)),
        batch_size=batch_size,
    )

    try:
        # Fast fail if MongoDB isn't reachable.
        build_client(cfg, compressors_override=None).admin.command("ping")
    except ServerSelectionTimeoutError as e:
        raise SystemExit(
            "MongoDB is not reachable at the configured URI.\n\n"
            f"URI: {cfg['mongodb']['uri']}\n\n"
            "If you're using this repo's Docker setup, fix it with:\n"
            "  cd ~/repos/mongodb_compress/deployment\n"
            "  sudo docker compose down\n"
            "  sudo rm -rf ../db/*\n"
            "  sudo docker compose up -d\n\n"
            f"Original error: {e}"
        )

    if bool(icfg.get("drop_collection_first", False)):
        client0 = build_client(cfg, compressors_override=None)
        coll0 = _make_collection(cfg, client0)
        coll0.drop()

    mdb = cfg["mongodb"]
    phase1_compressors = _normalize_compressors(
        mdb.get("network_payload_compressors_for_compression_run")
    )
    phase2_compressors = _normalize_compressors(
        mdb.get("network_payload_compressors_for_no_compression_run")
    )

    results_array: List[Dict[str, Any]] = []
    if run_comparison:
        phase1 = _run_phase(
            cfg=cfg,
            batches=batches,
            docs_total=docs_total,
            bytes_total_est=bytes_total,
            threads=threads,
            phase_name="compression",
            compressors_override=phase1_compressors,
        )
        results_array.append(phase1)

        client_purge = build_client(cfg, compressors_override=None)
        coll_purge = _make_collection(cfg, client_purge)
        coll_purge.drop()

        phase2 = _run_phase(
            cfg=cfg,
            batches=batches,
            docs_total=docs_total,
            bytes_total_est=bytes_total,
            threads=threads,
            phase_name="no_compression",
            compressors_override=phase2_compressors,
        )
        results_array.append(phase2)
        results_array.append(_compare_results(phase1, phase2))
    else:
        results_array.append(
            _run_phase(
                cfg=cfg,
                batches=batches,
                docs_total=docs_total,
                bytes_total_est=bytes_total,
                threads=threads,
                phase_name="single_run",
                compressors_override=phase1_compressors,
            )
        )

    configured_output = str(mcfg.get("output_path", "results.json"))
    if configured_output in ("results.json", "", "null"):
        output_path = _default_report_path(args.config)
    else:
        output_path = _resolve_output_path(args.config, configured_output)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"config_path": args.config, "results": results_array}, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"Wrote: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

