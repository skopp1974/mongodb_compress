import argparse
import os
import subprocess

from pymongo import MongoClient

from .load_test.run import build_client, load_config


def _run(cmd: list[str], *, cwd: str) -> None:
    """
    Run a command; if it fails due to docker-sock permissions, retry with sudo.
    """
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if res.returncode == 0:
        return

    combined = (res.stdout or "") + (res.stderr or "")
    needs_sudo = "permission denied while trying to connect to the docker api" in combined.lower()
    if needs_sudo and cmd[:1] != ["sudo"]:
        subprocess.run(["sudo", *cmd], cwd=cwd, check=True)
        return

    # Fall back to surfacing the original error.
    raise SystemExit(combined.strip() or f"Command failed: {' '.join(cmd)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge ingested data from MongoDB collection.")
    parser.add_argument("--config", required=True, help="Path to YAML config.")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop the collection instead of deleting documents.",
    )
    parser.add_argument(
        "--drop-db",
        action="store_true",
        help="Drop the entire database specified in the config.",
    )
    parser.add_argument(
        "--wipe-host-db-dir",
        action="store_true",
        help=(
            "Reclaim host disk space by stopping MongoDB (docker compose), deleting ../db/*, "
            "and starting it again. This is irreversible."
        ),
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    mcfg = cfg["mongodb"]

    client: MongoClient = build_client(cfg)
    db = client.get_database(mcfg["database"])
    coll = db.get_collection(mcfg["collection"])

    if args.wipe_host_db_dir:
        # Repo layout:
        # - <repo>/deployment/docker-compose.yml
        # - <repo>/db (bind mounted into MongoDB container)
        repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        deployment_dir = os.path.join(repo_root, "deployment")
        db_dir = os.path.join(repo_root, "db")

        if not os.path.isdir(deployment_dir):
            raise SystemExit(f"Expected deployment dir not found: {deployment_dir}")
        if not os.path.isdir(db_dir):
            raise SystemExit(f"Expected db dir not found: {db_dir}")

        # Stop MongoDB container(s)
        _run(["docker", "compose", "down"], cwd=deployment_dir)

        # Delete contents of db dir, but keep the directory itself.
        # Use sudo because container-created files may be owned by a different uid/gid.
        # Remove via Python; fallback to `sudo rm -rf` per-path if needed.
        for name in os.listdir(db_dir):
            p = os.path.join(db_dir, name)
            try:
                if os.path.isdir(p) and not os.path.islink(p):
                    subprocess.run(["rm", "-rf", p], check=False)
                else:
                    os.unlink(p)
            except PermissionError:
                subprocess.run(["sudo", "rm", "-rf", p], check=False)
            except FileNotFoundError:
                pass

        # Start MongoDB again (recreates compress_poc/init via initdb scripts if db was empty)
        _run(["docker", "compose", "up", "-d"], cwd=deployment_dir)
        print(f"Wiped host db dir contents: {db_dir}")
        return 0

    if args.drop_db:
        client.drop_database(mcfg["database"])
        print(f"Dropped database {mcfg['database']}")
        return 0

    if args.drop:
        coll.drop()
        print(f"Dropped {mcfg['database']}.{mcfg['collection']}")
        return 0

    res = coll.delete_many({})
    print(f"Deleted {res.deleted_count} docs from {mcfg['database']}.{mcfg['collection']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

