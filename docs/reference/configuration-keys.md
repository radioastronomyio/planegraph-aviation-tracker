<!--
---
title: "Configuration Keys"
description: "Pipeline configuration keys, default values, and hot-reload behavior"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: reference
  - domain: [ingest, materialization]
  - tech: postgres
  - audience: intermediate
related_documents:
  - "[Data Dictionary](data-dictionary.md)"
  - "[Docker Services](docker-services.md)"
---
-->

# Configuration Keys

All runtime configuration for the Planegraph pipeline is stored in the `pipeline_config` table as key-value pairs with JSONB values. Changes to any key emit a PostgreSQL `NOTIFY config_changed` event, allowing running services to hot-reload configuration without restart.

---

## 1. Key Inventory

### session_gap_threshold_sec

| Property | Value |
|----------|-------|
| Default | `300` |
| Type | Integer (seconds) |
| Used By | Ingest daemon (WU-02) |

The maximum time gap in seconds between consecutive position reports before the ingest daemon closes the current flight session and opens a new one. A value of 300 (5 minutes) means that if an aircraft disappears from the SBS stream for more than 5 minutes and then reappears, it is treated as a new session.

Lower values produce more sessions (splitting flights that briefly lose signal). Higher values merge longer gaps but risk combining separate flights from the same aircraft (e.g., a turnaround at a gate).

### batch_interval_sec

| Property | Value |
|----------|-------|
| Default | `2` |
| Type | Integer (seconds) |
| Used By | Ingest daemon (WU-02) |

How often the ingest daemon flushes its position report buffer to PostgreSQL. The daemon collects reports in memory and writes them in micro-batches using `COPY` or `UNNEST` for throughput. A value of 2 means a write every 2 seconds.

Lower values reduce data loss on crash but increase write frequency. Higher values improve throughput but increase the window of data at risk in memory.

### phase_classification

| Property | Value |
|----------|-------|
| Default | See below |
| Type | JSON object |
| Used By | Ingest daemon (WU-02) |

Fuzzy thresholds for classifying each position report into a flight phase. The ingest daemon evaluates these thresholds against speed, altitude, and vertical rate to assign one of: `ground`, `takeoff`, `climb`, `cruise`, `descent`, `approach`, `landing`.

Default thresholds:

```json
{
    "ground_speed_max_kts": 50,
    "ground_alt_agl_max_ft": 200,
    "takeoff_vrate_min_fpm": 200,
    "climb_vrate_min_fpm": 200,
    "cruise_alt_min_ft": 18000,
    "descent_vrate_max_fpm": -200,
    "approach_alt_max_ft": 5000,
    "approach_speed_max_kts": 200,
    "landing_vrate_max_fpm": -100,
    "landing_alt_agl_max_ft": 100
}
```

These values are tuned for the Columbus area traffic mix (commercial jets at KCMH, cargo at KLCK, GA at KOSU/KTZR). Adjust if the receiver covers a different airport profile.

### retention_days

| Property | Value |
|----------|-------|
| Default | `60` |
| Type | Integer (days) |
| Used By | Materializer `drop_expired_partitions()` (WU-02) |

Number of days of position report data to retain. The `drop_expired_partitions()` function drops daily partitions older than this value. A 256GB SSD at peak Columbus traffic rates can safely hold approximately 60–90 days of data.

Increasing this value requires monitoring disk usage. Decreasing it frees storage but loses historical data irreversibly.

---

## 2. Hot-Reload Mechanism

When any key in `pipeline_config` is inserted or updated, the database trigger `notify_config_changed()` fires, which:

1. Sets `updated_at` to `now()` on the modified row
2. Emits `pg_notify('config_changed', payload)` where payload is:

```json
{
    "key": "session_gap_threshold_sec",
    "value": 300,
    "updated_at": "2026-03-17T12:00:00Z"
}
```

Services that `LISTEN config_changed` receive this notification and reload the relevant parameter without restarting. This enables runtime tuning of phase classification thresholds, session gap behavior, and retention policy through the API or direct SQL.

---

## 3. Modifying Configuration

### Via SQL

```sql
UPDATE pipeline_config SET value = '600' WHERE key = 'session_gap_threshold_sec';
```

### Via API (WU-03+)

```bash
curl -X PUT http://localhost:8000/api/v1/config/session_gap_threshold_sec \
  -H "Content-Type: application/json" \
  -d '{"value": 600}'
```

### Via Dashboard (WU-05+)

The configuration page exposes all keys with type-appropriate editors and live preview of the notification event.

---

## 4. References

| Resource | Description |
|----------|-------------|
| [Data Dictionary](data-dictionary.md) | Full `pipeline_config` table definition |
| [WU-01 Spec](../../spec/wu-01-infrastructure/README.md) | Config trigger specification |

---

## 5. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
