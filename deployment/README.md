# Local MongoDB (Docker) POC

This is the simplest way to run MongoDB locally on a Chromebook / Linux machine.

## Prereqs

- Docker
- Docker Compose (either `docker compose` plugin or `docker-compose`)

## Start MongoDB (no auth)

From `mongodb_compress/deployment`:

```bash
docker compose up -d
```

MongoDB will be reachable at `mongodb://localhost:27017`.

## Initialized database

On first startup (when `../db/` is empty), the container runs `deployment/initdb/01-create-compress-poc.js` and creates:

- database: `compress_poc`
- collection: `init`

## Start MongoDB (with auth)

```bash
cp .env.example .env
# edit .env and set a strong password
docker compose up -d
```

Connect with:

```bash
mongosh "mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/admin"
```

## View logs

```bash
docker compose logs -f mongodb
```

## Stop

```bash
docker compose down
```

## Uninstall / wipe all data

Warning: this deletes all MongoDB data stored under `../db/`.

```bash
docker compose down -v
```

