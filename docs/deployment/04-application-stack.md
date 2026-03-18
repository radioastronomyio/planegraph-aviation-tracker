<!--
---
title: "Application Stack"
description: "Docker Compose deployment, database initialization, and migration execution"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: guide
  - domain: deployment
  - tech: [docker, postgres, postgis, readsb]
  - audience: intermediate
related_documents:
  - "[Docker Services Reference](../reference/docker-services.md)"
  - "[Data Dictionary](../reference/data-dictionary.md)"
  - "[Verification](05-verification.md)"
---
-->

# Application Stack

Deploy the Docker Compose stack (PostgreSQL + ultrafeeder), configure the environment, and run database migrations. This step produces a running system with an initialized database and live ADS-B reception.

---

## 1. Purpose

Stand up the two core containers (PostGIS database and ultrafeeder ADS-B receiver), configure them for the local environment, create the database schema, seed reference geometry for Columbus-area airports, and bootstrap daily partitions.

---

## 2. Prerequisites

- Ubuntu 24.04 configured, hardened, and SDR-verified per steps [01](01-ubuntu-base.md)–[03](03-sdr-configuration.md)
- Docker and Docker Compose installed and operational
- Repository cloned to the working directory
- `postgresql-client` installed for running migrations

---

## 3. Environment Configuration

Copy the environment template and configure for your site:

```bash
cd /path/to/planegraph-aviation-tracker
cp docker/.env.example docker/.env
```

Edit `docker/.env` and set:

```dotenv
# REQUIRED: Set a strong password
POSTGRES_PASSWORD=your_secure_password_here

# REQUIRED: Set your receiver location (decimal degrees, meters MSL)
RECEIVER_LAT=39.94
RECEIVER_LON=-83.07
RECEIVER_ALT=280
```

The receiver coordinates are used by ultrafeeder for MLAT calculations and by tar1090 for map centering. Use your actual antenna location — the Columbus defaults in `.env.example` are approximate.

All other values in `.env.example` have sensible defaults and can be left as-is for initial deployment.

---

## 4. Start the Stack

```bash
docker compose -f docker/docker-compose.yml up -d
```

Verify both containers are running:

```bash
docker compose -f docker/docker-compose.yml ps
```

Expected output shows `planegraph-postgres` and `planegraph-ultrafeeder` both in `running` state with `healthy` status for Postgres (may take 10–20 seconds for the health check to pass).

---

## 5. Run Database Migrations

The migration runner reads connection parameters from `docker/.env` and executes all numbered SQL files in order:

```bash
bash migrations/run.sh
```

Expected output:

```
Connecting to localhost:5432 as planegraph @ planegraph
Applying: 001_core_schema.sql
  OK: 001_core_schema.sql
Applying: 002_reference_geometry_schema.sql
  OK: 002_reference_geometry_schema.sql
Applying: 003_seed_airports_runways.sql
  OK: 003_seed_airports_runways.sql
Applying: 004_seed_airspace_boundaries.sql
  OK: 004_seed_airspace_boundaries.sql
Applying: 005_seed_points_of_interest.sql
  OK: 005_seed_points_of_interest.sql
Applying: 006_partition_management.sql
  OK: 006_partition_management.sql

All migrations complete.
```

If any migration fails, the runner stops immediately. Fix the issue and re-run — migrations use `IF NOT EXISTS` and `ON CONFLICT` where possible for idempotency.

---

## 6. Verify Core Services

### PostgreSQL

```bash
# Health check
docker compose -f docker/docker-compose.yml exec planegraph-postgres pg_isready -U planegraph
# Expected: "accepting connections"

# PostGIS loaded
psql -h localhost -U planegraph -d planegraph -tAc "SELECT postgis_version();"
# Expected: version string (e.g., "3.4 USE_GEOS=1 USE_PROJ=1 USE_STATS=1")
```

### Ultrafeeder

```bash
# tar1090 web UI
curl -sf http://localhost:8080/data/aircraft.json | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'Aircraft: {len(d.get(\"aircraft\", []))}')"
# Expected: "Aircraft: N" where N is the number of currently visible aircraft

# SBS output port
nc -z localhost 30003
# Expected: exit code 0

# Beast output port
nc -z localhost 30005
# Expected: exit code 0
```

The tar1090 web UI is also accessible in a browser at `http://<edge02-ip>:8080` for visual verification.

---

## 7. Verify Database Content

```bash
psql -h localhost -U planegraph -d planegraph -tAc "
  SELECT 'airports: ' || count(*) FROM airports
  UNION ALL SELECT 'runways: ' || count(*) FROM runways
  UNION ALL SELECT 'airspace: ' || count(*) FROM airspace_boundaries
  UNION ALL SELECT 'pois: ' || count(*) FROM points_of_interest
  UNION ALL SELECT 'partitions: ' || count(*) FROM pg_inherits WHERE inhparent = 'position_reports'::regclass
  UNION ALL SELECT 'config keys: ' || count(*) FROM pipeline_config;
"
```

Expected counts: airports: 4, runways: 16, airspace: 5, pois: 16, partitions: 4+, config keys: 4.

---

## 8. Next Step

Proceed to [Verification](05-verification.md) for the full acceptance test suite.

---

## 9. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
