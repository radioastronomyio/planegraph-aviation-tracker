<!--
---
title: "Ingest Service"
description: "Asyncio SBS consumer, session manager, and batch writer"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Planned"
tags:
  - type: directory-readme
  - domain: ingest
  - tech: [python, postgres, asyncio]
---
-->

# Ingest Service

Asyncio daemon that consumes decoded ADS-B messages from ultrafeeder's SBS port (30003), segments aircraft tracks into flight sessions, classifies flight phases using fuzzy heuristics, and batch-writes position reports to PostgreSQL.

**Status**: 📋 Planned (WU-02)

---

## 1. Contents

```
ingest/
├── README.md               # This file
└── [WU-02 deliverables]    # Created during WU-02 implementation
```

---

## 2. Design Summary

The ingest daemon is the core data pipeline. It maintains per-ICAO session state in memory, accumulates position reports across SBS message subtypes (MSG,1 through MSG,8), and flushes to Postgres in configurable micro-batches.

Key behaviors:

- Connects to `localhost:30003` via asyncio TCP
- Merges MSG,3 (position) and MSG,4 (velocity) into unified aircraft state
- Segments flights using `session_gap_threshold_sec` from `pipeline_config`
- Classifies phases using `phase_classification` thresholds
- Batch-writes via `COPY` or `UNNEST` every `batch_interval_sec` seconds
- Listens for `config_changed` NOTIFY for hot-reload of all parameters

---

## 3. Expected Components

| Component | File | Purpose |
|-----------|------|---------|
| SBS Reader | `sbs_reader.py` | TCP consumer, CSV line parser, message type routing |
| Session Manager | `session_manager.py` | Per-ICAO state machine, gap detection, phase classification |
| Batch Writer | `batch_writer.py` | Micro-batch accumulator, COPY/UNNEST flush to Postgres |
| Config Listener | `config_listener.py` | PostgreSQL LISTEN for hot-reload |
| Main | `main.py` | Asyncio event loop, service lifecycle, graceful shutdown |

<!-- CC: When WU-02 code exists, update this README to document:
     - Actual file inventory and module responsibilities
     - Configuration parameters consumed (from pipeline_config)
     - Startup command and environment requirements
     - Health indicators and monitoring endpoints
     - Performance characteristics (messages/sec, batch sizes, memory footprint)
     - Failure modes and recovery behavior
-->

---

## 4. Related

| Document | Relationship |
|----------|--------------|
| [Services](../README.md) | Parent directory |
| [Data Dictionary](../../docs/reference/data-dictionary.md) | Schema written to |
| [Configuration Keys](../../docs/reference/configuration-keys.md) | Runtime parameters consumed |
| [Docker Services](../../docs/reference/docker-services.md) | ultrafeeder SBS source |
