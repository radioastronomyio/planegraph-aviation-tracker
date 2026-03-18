<!--
---
title: "API Service"
description: "FastAPI REST endpoints and WebSocket live aircraft feed"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Planned"
tags:
  - type: directory-readme
  - domain: api
  - tech: [python, fastapi, websocket]
---
-->

# API Service

FastAPI application serving REST endpoints for flight queries, configuration management, and system health, plus a WebSocket endpoint for live aircraft position streaming to the frontend.

**Status**: 📋 Planned (WU-03)

---

## 1. Contents

```
api/
├── README.md               # This file
└── [WU-03 deliverables]    # Created during WU-03 implementation
```

---

## 2. Design Summary

The API is the single interface between the database and all consumers — the React frontend, external scripts, and the planned AI query interface. It exposes both historical query endpoints and a real-time WebSocket feed.

Key capabilities:

- REST endpoints for flight session queries (by time range, airport, aircraft, phase)
- REST endpoints for reference data (airports, runways, airspace, POIs)
- REST endpoints for pipeline configuration (CRUD on `pipeline_config`)
- REST endpoint for system health and statistics
- WebSocket endpoint streaming live aircraft positions from the ingest daemon
- OpenAPI/Swagger documentation auto-generated

---

## 3. Expected Components

| Component | File | Purpose |
|-----------|------|---------|
| Application | `app.py` | FastAPI app factory, middleware, CORS |
| Flight Routes | `routes/flights.py` | Flight session and position query endpoints |
| Reference Routes | `routes/reference.py` | Airport, runway, airspace, POI endpoints |
| Config Routes | `routes/config.py` | Pipeline configuration CRUD |
| Health Routes | `routes/health.py` | System and container health endpoints |
| WebSocket | `ws/live_feed.py` | Real-time aircraft position broadcast |
| Database | `db.py` | Connection pool and query helpers |

<!-- CC: When WU-03 code exists, update this README to document:
     - Actual file inventory and module responsibilities
     - Full endpoint inventory with request/response examples
     - WebSocket message format and subscription model
     - Authentication model (if implemented)
     - Rate limiting and connection limits
     - Performance characteristics (query latency, WebSocket throughput)
-->

---

## 4. Related

| Document | Relationship |
|----------|--------------|
| [Services](../README.md) | Parent directory |
| [Data Dictionary](../../docs/reference/data-dictionary.md) | Schema queried |
| [Configuration Keys](../../docs/reference/configuration-keys.md) | Config endpoints serve these |
| [Docker Services](../../docs/reference/docker-services.md) | Will be added as a service |
