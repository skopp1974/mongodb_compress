import argparse

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
    args = parser.parse_args()

    cfg = load_config(args.config)
    mcfg = cfg["mongodb"]

    client: MongoClient = build_client(cfg)
    db = client.get_database(mcfg["database"])
    coll = db.get_collection(mcfg["collection"])

    if args.drop:
        coll.drop()
        print(f"Dropped {mcfg['database']}.{mcfg['collection']}")
        return 0

    res = coll.delete_many({})
    print(f"Deleted {res.deleted_count} docs from {mcfg['database']}.{mcfg['collection']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

