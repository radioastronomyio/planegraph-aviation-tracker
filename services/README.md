<!--
---
title: "Services"
description: "Application services for ingest, materialization, and API"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: [ingest, materialization, api]
  - tech: [python, fastapi]
---
-->

# Services

Application services that consume, process, and serve aviation data. All services are Python 3.11+ and connect to the PostgreSQL instance defined in `docker/`.

---

## 1. Contents

```
services/
├── ingest/          # SBS stream consumer and session manager (WU-02)
├── materializer/    # Scheduled flight materialization and partition management (WU-02)
├── api/             # FastAPI REST + WebSocket live feed (WU-03)
└── README.md        # This file
```

---

## 2. Components

| Component | Description | Status |
|-----------|-------------|--------|
| [ingest/](ingest/) | Asyncio daemon consuming SBS from ultrafeeder port 30003, segmenting flights, batch-writing to Postgres | 📋 Planned (WU-02) |
| [materializer/](materializer/) | Scheduled worker computing flight metrics, managing daily partitions, enforcing retention | 📋 Planned (WU-02) |
| [api/](api/) | FastAPI application serving REST queries, WebSocket live feed, and configuration endpoints | 📋 Planned (WU-03) |

---

## 3. Related

| Document | Relationship |
|----------|--------------|
| [Repository Root](../README.md) | Parent directory |
| [Docker](../docker/README.md) | Container stack these services connect to |
| [Migrations](../migrations/README.md) | Schema these services operate on |
