import argparse
import os
import shutil
import subprocess

from pymongo import MongoClient

from .load_test.run import build_client, load_config


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
        subprocess.run(["docker", "compose", "down"], cwd=deployment_dir, check=False)

        # Delete contents of db dir, but keep the directory itself.
        for name in os.listdir(db_dir):
            p = os.path.join(db_dir, name)
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                try:
                    os.unlink(p)
                except FileNotFoundError:
                    pass

        # Start MongoDB again (recreates compress_poc/init via initdb scripts if db was empty)
        subprocess.run(["docker", "compose", "up", "-d"], cwd=deployment_dir, check=False)
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

