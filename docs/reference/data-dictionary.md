<!--
---
title: "Data Dictionary"
description: "Column-level reference for all database tables with aviation domain context"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: reference
  - domain: schema
  - tech: [postgres, postgis]
  - audience: all
related_documents:
  - "[Configuration Keys](configuration-keys.md)"
  - "[Migrations](../../migrations/README.md)"
---
-->

# Data Dictionary

Column-level reference for every table in the Planegraph database. Each table includes column definitions, types, constraints, and domain context explaining what the data means in aviation terms.

Source: `migrations/001_core_schema.sql` through `migrations/006_partition_management.sql`.

---

## 1. Core Tables

### 1.1 flight_sessions

A flight session represents a single continuous observation of an aircraft. Sessions are created when a new hex code appears in the SBS stream and closed when no position reports are received for the configured gap threshold (default: 300 seconds). One physical flight may produce multiple sessions if signal is lost and reacquired.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `session_id` | `uuid` | No | `gen_random_uuid()` | Primary key. Unique session identifier. |
| `hex` | `char(6)` | No | — | ICAO 24-bit aircraft address in hex (e.g., `a12345`). This is the aircraft's permanent identity, not the flight number. |
| `callsign` | `varchar(10)` | Yes | — | Flight identifier broadcast by the aircraft (e.g., `UAL1234`, `N12345`). May be null if the aircraft doesn't broadcast one, or may change mid-session for repositioning flights. |
| `started_at` | `timestamptz` | No | — | Timestamp of the first position report in this session. |
| `ended_at` | `timestamptz` | Yes | — | Timestamp of the last position report. Null while the session is still active. |
| `on_ground` | `boolean` | No | `false` | Whether the aircraft was on the ground at session start. Derived from the first position report's ground flag. |
| `departure_airport_icao` | `char(4)` | Yes | — | ICAO code of the departure airport if determined by spatial proximity to a runway at session start. |
| `arrival_airport_icao` | `char(4)` | Yes | — | ICAO code of the arrival airport if determined by spatial proximity to a runway at session end. |
| `total_distance_nm` | `numeric(10,2)` | Yes | — | Great-circle distance of the trajectory in nautical miles. Computed during materialization. |
| `trajectory_geom` | `geometry(linestringz, 4326)` | Yes | — | Full 3D trajectory as a PostGIS LineStringZ (lon, lat, altitude). Built from position reports during materialization. |
| `created_at` | `timestamptz` | No | `now()` | Row creation timestamp. |
| `updated_at` | `timestamptz` | No | `now()` | Last modification timestamp. Updated by the materialization process. |

Indexes: `hex`, `started_at DESC`, `ended_at` (partial, where not null), `callsign` (partial, where not null).

### 1.2 position_reports

Individual aircraft position observations decoded from the ADS-B SBS stream. This is the highest-volume table — expect 1,000–10,000+ rows per minute depending on traffic density. Partitioned by `report_time` into daily partitions (`position_reports_YYYYMMDD`).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `report_id` | `bigserial` | No | Auto-increment | Row identifier. Not globally unique across partitions. |
| `session_id` | `uuid` | No | — | Foreign key to `flight_sessions`. Links this report to its parent session. |
| `hex` | `char(6)` | No | — | ICAO 24-bit aircraft address. Denormalized from session for query performance. |
| `report_time` | `timestamptz` | No | — | Timestamp when this position was decoded. Partition key. |
| `lat` | `numeric(10,6)` | No | — | Latitude in decimal degrees (WGS84). Positive = north. |
| `lon` | `numeric(10,6)` | No | — | Longitude in decimal degrees (WGS84). Positive = east. |
| `alt_ft` | `integer` | Yes | — | Barometric altitude in feet MSL. Null if aircraft is not broadcasting altitude (rare for ADS-B equipped aircraft). |
| `track` | `numeric(5,1)` | Yes | — | Ground track in degrees true (0–359.9). The direction the aircraft is moving, not the direction it's pointing (heading). |
| `speed_kts` | `integer` | Yes | — | Ground speed in knots. |
| `vrate_fpm` | `integer` | Yes | — | Vertical rate in feet per minute. Positive = climbing, negative = descending. |
| `phase` | `varchar(10)` | Yes | — | Flight phase classification: `ground`, `takeoff`, `climb`, `cruise`, `descent`, `approach`, `landing`. Assigned by the ingest pipeline using fuzzy thresholds from `pipeline_config`. |
| `squawk` | `varchar(4)` | Yes | — | 4-digit transponder code assigned by ATC (e.g., `1200` = VFR, `7700` = emergency, `7600` = comms failure). |
| `on_ground` | `boolean` | No | `false` | Whether the aircraft reports being on the ground. Derived from the ADS-B surface position message type. |
| `category` | `varchar(4)` | Yes | — | Aircraft category from ADS-B message (e.g., `A1`=light, `A3`=large, `A5`=heavy, `B2`=balloon). |
| `geom` | `geometry(pointz, 4326)` | Yes | — | PostGIS 3D point (lon, lat, altitude). Populated during ingest for spatial queries. |

Indexes: `session_id`, `hex`, `report_time DESC`.

Partitioning: Range partitioned on `report_time`. Daily partitions created by `create_daily_partition()`. Expired partitions dropped by `drop_expired_partitions()` based on `retention_days` config.

### 1.3 pipeline_config

Key-value configuration store for all pipeline parameters. Changes trigger `NOTIFY config_changed` so running services can hot-reload without restart.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `key` | `varchar(64)` | No | — | Configuration key name. Primary key. |
| `value` | `jsonb` | No | — | Configuration value as JSONB. Scalar values are stored as JSON primitives (e.g., `300` not `"300"`). Complex values are JSON objects. |
| `updated_at` | `timestamptz` | No | `now()` | Last modification timestamp. Automatically updated by the notification trigger. |

Triggers: `trg_pipeline_config_changed` (BEFORE UPDATE) and `trg_pipeline_config_inserted` (BEFORE INSERT) both fire `notify_config_changed()`, which sets `updated_at` and emits a `pg_notify('config_changed', ...)` payload.

See [Configuration Keys](configuration-keys.md) for the full key inventory.

### 1.4 materialization_log

Tracks when flight sessions are materialized (trajectory built, metrics computed). Enables the materializer to skip already-processed sessions and to re-materialize if needed.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `session_id` | `uuid` | No | — | Foreign key to `flight_sessions`. Composite primary key with `materialized_at`. |
| `materialized_at` | `timestamptz` | No | `now()` | When materialization occurred. Multiple entries per session are possible (re-materialization). |
| `distance_nm` | `numeric(10,2)` | Yes | — | Computed trajectory distance at time of materialization. |
| `phase_summary` | `jsonb` | Yes | — | JSON summary of time spent in each flight phase (e.g., `{"climb": 342, "cruise": 1800, "descent": 480}` in seconds). |

---

## 2. Reference Geometry Tables

### 2.1 airports

The four Columbus-area airports tracked by this system. Used for departure/arrival airport assignment via spatial proximity to runway thresholds.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `icao` | `char(4)` | No | — | ICAO airport identifier. Primary key. |
| `name` | `varchar(100)` | No | — | Full airport name. |
| `city` | `varchar(60)` | Yes | — | City name. |
| `lat` | `numeric(10,6)` | No | — | Airport reference point latitude. |
| `lon` | `numeric(10,6)` | No | — | Airport reference point longitude. |
| `elevation_ft` | `integer` | No | — | Field elevation in feet MSL. |
| `geom` | `geometry(point, 4326)` | Yes | — | PostGIS point at the airport reference coordinates. |

Seeded airports: KCMH (John Glenn Columbus International), KLCK (Rickenbacker International), KOSU (Ohio State University Airport), KTZR (Bolton Field).

### 2.2 runways

Runway threshold positions with extended centerlines for approach path analysis. Each physical runway end is a separate row (e.g., runway 10L/28R produces two rows: one for the 10L threshold and one for the 28R threshold).

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `runway_id` | `serial` | No | Auto-increment | Primary key. |
| `airport_icao` | `char(4)` | No | — | Foreign key to `airports`. |
| `designator` | `varchar(5)` | No | — | Runway designator (e.g., `10L`, `28R`, `04`, `22`). |
| `heading_true` | `numeric(5,1)` | No | — | Runway heading in degrees true. This is the direction of travel when using this runway end for takeoff/landing. |
| `threshold_lat` | `numeric(10,6)` | No | — | Threshold latitude. |
| `threshold_lon` | `numeric(10,6)` | No | — | Threshold longitude. |
| `threshold_elevation_ft` | `integer` | No | — | Threshold elevation in feet MSL. |
| `threshold_geom` | `geometry(point, 4326)` | Yes | — | PostGIS point at the threshold. |
| `extended_centerline_geom` | `geometry(linestring, 4326)` | Yes | — | 15 NM (27,780 m) line extending from the threshold in the approach direction (opposite of runway heading). Used for approach path deviation analysis. Generated with `ST_Project` over geography. |

Unique constraint: `(airport_icao, designator)`.

16 rows total: 4 per airport (KCMH has 10L/28R/10R/28L; KLCK has 05L/23R/05R/23L; KOSU has 09L/27R/09R/27L; KTZR has 04/22/13/31).

### 2.3 airspace_boundaries

Controlled airspace volumes around each airport. Used for determining when aircraft enter or exit controlled airspace and for spatial filtering.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `boundary_id` | `serial` | No | Auto-increment | Primary key. |
| `name` | `varchar(100)` | No | — | Descriptive name (e.g., `KCMH Class C Surface`). |
| `class` | `varchar(10)` | No | — | Airspace classification (`C` or `D` in this dataset). |
| `floor_ft` | `integer` | No | — | Lower altitude limit in feet MSL. 0 = surface. |
| `ceiling_ft` | `integer` | No | — | Upper altitude limit in feet MSL. |
| `geom` | `geometry(polygon, 4326)` | Yes | — | Airspace boundary polygon. Generated with geodetic `ST_Buffer` for accurate circles. |

5 rows: KCMH Class C surface (5 NM, SFC–4000), KCMH Class C shelf (10 NM, 1200–4000), KLCK Class D (4.4 NM, SFC–2900), KOSU Class D (4.4 NM, SFC–3200), KTZR Class D (4.4 NM, SFC–3200).

### 2.4 points_of_interest

Notable locations for monitoring overflights, identifying approach fixes, and enriching flight context.

| Column | Type | Nullable | Default | Description |
|--------|------|----------|---------|-------------|
| `poi_id` | `serial` | No | Auto-increment | Primary key. |
| `name` | `varchar(100)` | No | — | Display name. |
| `type` | `varchar(50)` | No | — | Category: `approach_fix`, `navaid`, `overflight_zone`, `traffic_pattern`. |
| `lat` | `numeric(10,6)` | No | — | Latitude. |
| `lon` | `numeric(10,6)` | No | — | Longitude. |
| `radius_nm` | `numeric(4,1)` | No | `1.0` | Monitoring radius in nautical miles. Used to generate geofence buffers. |
| `geom` | `geometry(point, 4326)` | Yes | — | PostGIS point at the POI coordinates. |

16 rows across four categories: 8 approach fixes (final approach references for primary runways), 4 navaids (CMH VORTAC, Appleton VOR, Zanesville VOR, Falmouth VOR), 4 overflight zones (Downtown Columbus, OSU Campus, Rickenbacker Cargo Ramp, Bolton Field Pattern).

---

## 3. Partition Management Functions

### create_daily_partition(target_date date)

Creates a single daily partition of `position_reports` named `position_reports_YYYYMMDD`. Idempotent — skips creation if the partition already exists. Called during bootstrap (today + 3 days) and by the Python scheduler daily.

### drop_expired_partitions()

Drops partitions whose date range falls entirely before `now() - retention_days`. Reads `retention_days` from `pipeline_config` (default: 60). Called by the Python scheduler daily.

---

## 4. References

| Resource | Description |
|----------|-------------|
| [Configuration Keys](configuration-keys.md) | Pipeline config key inventory |
| [Migrations](../../migrations/README.md) | SQL source files |

---

## 5. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
