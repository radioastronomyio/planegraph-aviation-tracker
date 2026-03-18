<!--
---
title: "Migrations"
description: "Numbered SQL migrations for schema creation and reference data seeding"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: schema
  - tech: [postgres, postgis]
---
-->

# Migrations

Numbered SQL migrations executed in lexical order by `run.sh`. Creates the core schema, reference geometry tables, seeds Columbus-area aviation data, and bootstraps daily partitions.

---

## 1. Contents

```
migrations/
├── 001_core_schema.sql                 # flight_sessions, position_reports, pipeline_config, triggers
├── 002_reference_geometry_schema.sql   # airports, runways, airspace_boundaries, points_of_interest
├── 003_seed_airports_runways.sql       # 4 airports, 16 runway thresholds with extended centerlines
├── 004_seed_airspace_boundaries.sql    # 5 airspace boundaries (KCMH Class C, 3x Class D)
├── 005_seed_points_of_interest.sql     # 16 POIs (approach fixes, navaids, overflight zones)
├── 006_partition_management.sql        # Partition create/drop functions, bootstrap today + 3 days
├── run.sh                              # Migration runner (lexical order, stop on failure)
└── README.md                           # This file
```

---

## 2. Migration Inventory

| Migration | Creates | Row Counts |
|-----------|---------|------------|
| 001 | `flight_sessions`, `position_reports` (partitioned), `pipeline_config`, `materialization_log`, config triggers | 4 config keys |
| 002 | `airports`, `runways`, `airspace_boundaries`, `points_of_interest` | Schema only |
| 003 | Seed airports and runways with ST_Project centerlines | 4 airports, 16 runways |
| 004 | Seed airspace boundaries with geodetic ST_Buffer | 5 boundaries |
| 005 | Seed points of interest | 16 POIs |
| 006 | `create_daily_partition()`, `drop_expired_partitions()`, bootstrap | 4+ partitions |

---

## 3. Usage

Requires a running PostgreSQL instance (see `docker/`):

```bash
bash migrations/run.sh
```

The runner reads connection parameters from `docker/.env`, waits up to 30 seconds for Postgres readiness, then applies each `.sql` file in order. Stops on first failure.

---

## 4. Related

| Document | Relationship |
|----------|--------------|
| [Repository Root](../README.md) | Parent directory |
| [Docker](../docker/README.md) | Container stack that hosts the database |
| [Services](../services/README.md) | Application services that consume this schema |
