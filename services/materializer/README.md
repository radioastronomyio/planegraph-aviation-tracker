<!--
---
title: "Materializer Service"
description: "Scheduled flight metric computation, partition management, and retention enforcement"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Planned"
tags:
  - type: directory-readme
  - domain: materialization
  - tech: [python, postgres]
---
-->

# Materializer Service

Scheduled worker that computes derived flight metrics from raw position reports, manages daily table partitions, and enforces data retention policy. Runs on a configurable schedule alongside the ingest daemon.

**Status**: 📋 Planned (WU-02)

---

## 1. Contents

```
materializer/
├── README.md               # This file
└── [WU-02 deliverables]    # Created during WU-02 implementation
```

---

## 2. Design Summary

The materializer closes the loop between raw position data and queryable flight metrics. It operates on completed flight sessions, computing aggregates that the API and dashboard consume.

Key responsibilities:

- Compute flight session summaries (duration, distance, max altitude, average speed)
- Create tomorrow's daily partition via `create_daily_partition()`
- Drop expired partitions via `drop_expired_partitions()` per `retention_days` config
- Log all materialization runs to `materialization_log` for observability
- Run on a configurable schedule (default: every 5 minutes for metrics, daily for partitions)

---

## 3. Expected Components

| Component | File | Purpose |
|-----------|------|---------|
| Flight Materializer | `flight_materializer.py` | Session metric computation |
| Partition Manager | `partition_manager.py` | Daily partition lifecycle |
| Scheduler | `scheduler.py` | Periodic task runner |
| Main | `main.py` | Service lifecycle and graceful shutdown |

<!-- CC: When WU-02 code exists, update this README to document:
     - Actual file inventory and module responsibilities
     - Materialization queries and their outputs
     - Partition management schedule and behavior
     - Performance characteristics (materialization duration, partition sizes)
     - Interaction with materialization_log table
     - Failure modes and idempotency guarantees
-->

---

## 4. Related

| Document | Relationship |
|----------|--------------|
| [Services](../README.md) | Parent directory |
| [Data Dictionary](../../docs/reference/data-dictionary.md) | Schema operated on |
| [Configuration Keys](../../docs/reference/configuration-keys.md) | retention_days and schedule parameters |
