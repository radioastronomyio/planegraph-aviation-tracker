<!--
---
title: "Verification"
description: "End-to-end acceptance testing for the deployed Planegraph stack"
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
  - "[Application Stack](04-application-stack.md)"
  - "[Data Dictionary](../reference/data-dictionary.md)"
---
-->

# Verification

End-to-end acceptance tests confirming the Planegraph platform is correctly deployed and operational. Run these checks after completing the deployment sequence.

---

## 1. Purpose

Validate that all components — containers, database, schema, seed data, partitions, triggers, and ADS-B reception — are functioning correctly. Every test has a specific expected output. If any test fails, the deployment is not complete.

---

## 2. Prerequisites

- Full deployment completed per steps [01](01-ubuntu-base.md)–[04](04-application-stack.md)
- Both containers running
- Migrations applied successfully

---

## 3. Acceptance Tests

### Test 1: Containers Running

```bash
docker compose -f docker/docker-compose.yml ps
```

**Pass**: Both `planegraph-postgres` and `planegraph-ultrafeeder` show `running` state.

### Test 2: PostgreSQL Health

```bash
docker compose -f docker/docker-compose.yml exec planegraph-postgres pg_isready -U planegraph
```

**Pass**: Output contains `accepting connections`.

### Test 3: PostGIS Extension

```bash
psql -h localhost -U planegraph -d planegraph -tAc "SELECT postgis_version();"
```

**Pass**: Returns a non-empty version string.

### Test 4: Core Table Row Counts

```bash
psql -h localhost -U planegraph -d planegraph -tAc "
  SELECT count(*) FROM airports;
  SELECT count(*) FROM runways;
  SELECT count(*) FROM airspace_boundaries;
  SELECT count(*) FROM points_of_interest;
"
```

**Pass**: Returns `4`, `16`, `5`, `16` in that order.

### Test 5: Partition Bootstrap

```bash
psql -h localhost -U planegraph -d planegraph -tAc "
  SELECT count(*) FROM pg_inherits WHERE inhparent = 'position_reports'::regclass;
"
```

**Pass**: Count is 4 or greater (today + 3 future days).

### Test 6: Config Notification Trigger

```bash
psql -h localhost -U planegraph -d planegraph -tAc "
  SELECT tgname FROM pg_trigger WHERE tgname = 'trg_pipeline_config_changed';
"
```

**Pass**: Returns `trg_pipeline_config_changed`.

### Test 7: Ultrafeeder Aircraft JSON

```bash
curl -sf http://localhost:8080/data/aircraft.json | python3 -c "import sys, json; d=json.load(sys.stdin); print('aircraft' in d)"
```

**Pass**: Prints `True`.

### Test 8: SBS Output Port

```bash
nc -z localhost 30003
```

**Pass**: Exits with code 0.

### Test 9: Extended Centerline Length

```bash
psql -h localhost -U planegraph -d planegraph -tAc "
  SELECT designator, round(st_length(extended_centerline_geom::geography))
  FROM runways ORDER BY 1 LIMIT 4;
"
```

**Pass**: Each returned length is approximately 27780 meters (15 NM). Slight variations due to geodetic projection are expected — values should be within 50 meters of 27780.

### Test 10: Config Trigger Fires

```bash
# In one terminal, listen for notifications:
psql -h localhost -U planegraph -d planegraph -c "LISTEN config_changed; SELECT 1; \\watch 1"

# In another terminal, update a config value:
psql -h localhost -U planegraph -d planegraph -c "UPDATE pipeline_config SET value = '300' WHERE key = 'session_gap_threshold_sec';"

# The first terminal should show an async notification.
```

**Pass**: The LISTEN terminal receives a notification containing `session_gap_threshold_sec`.

---

## 4. Quick Verification Script

For convenience, a combined check:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Planegraph Verification ==="

echo -n "Containers: "
docker compose -f docker/docker-compose.yml ps --format '{{.Name}}: {{.Status}}' 2>/dev/null | tr '\n' ' '
echo ""

echo -n "Postgres: "
docker compose -f docker/docker-compose.yml exec -T planegraph-postgres pg_isready -U planegraph 2>/dev/null | tail -1

echo -n "PostGIS: "
psql -h localhost -U planegraph -d planegraph -tAc "SELECT postgis_version();" 2>/dev/null

echo -n "Airports: "
psql -h localhost -U planegraph -d planegraph -tAc "SELECT count(*) FROM airports;" 2>/dev/null

echo -n "Runways: "
psql -h localhost -U planegraph -d planegraph -tAc "SELECT count(*) FROM runways;" 2>/dev/null

echo -n "Airspace: "
psql -h localhost -U planegraph -d planegraph -tAc "SELECT count(*) FROM airspace_boundaries;" 2>/dev/null

echo -n "POIs: "
psql -h localhost -U planegraph -d planegraph -tAc "SELECT count(*) FROM points_of_interest;" 2>/dev/null

echo -n "Partitions: "
psql -h localhost -U planegraph -d planegraph -tAc "SELECT count(*) FROM pg_inherits WHERE inhparent = 'position_reports'::regclass;" 2>/dev/null

echo -n "Trigger: "
psql -h localhost -U planegraph -d planegraph -tAc "SELECT tgname FROM pg_trigger WHERE tgname = 'trg_pipeline_config_changed';" 2>/dev/null

echo -n "Aircraft JSON: "
curl -sf http://localhost:8080/data/aircraft.json | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'{len(d.get(\"aircraft\", []))} aircraft visible')" 2>/dev/null

echo -n "SBS port: "
nc -z localhost 30003 && echo "open" || echo "closed"

echo ""
echo "=== Verification Complete ==="
```

---

## 5. Post-Verification

Once all tests pass, the system is operational. Next steps:

- Bookmark `http://<edge02-ip>:8080` for the tar1090 live map (validation UI)
- Proceed to WU-02 (Ingest Pipeline) for the Python SBS consumer
- Review [Operations Guide](../operations/README.md) for ongoing management

---

## 6. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
