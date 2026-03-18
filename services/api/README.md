<!--
---
title: "API Service"
description: "FastAPI REST endpoints and WebSocket live aircraft feed"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.1"
status: "Complete"
tags:
  - type: directory-readme
  - domain: api
  - tech: [python, fastapi, websocket, asyncpg]
---
-->

# API Service

FastAPI application serving REST endpoints for flight queries, configuration management, and system health, plus a WebSocket endpoint for live aircraft position streaming to the frontend.

**Status**: ✅ Complete (WU-03)

---

## 1. Contents

```
api/
├── README.md               # This file
├── __init__.py
├── main.py                 # App factory, lifespan, background tasks
├── db.py                   # asyncpg pool factory
├── dependencies.py         # FastAPI Depends() injectors
├── live_state.py           # In-memory live aircraft cache
├── routes/
│   ├── __init__.py
│   ├── aircraft.py         # GET /api/v1/aircraft (live cache)
│   ├── airspace.py         # GET /api/v1/airspace (reference geometry)
│   ├── config.py           # GET /api/v1/config, PATCH /api/v1/config/{key}
│   ├── flights.py          # GET /api/v1/flights, GET /api/v1/flights/{id}
│   ├── health.py           # GET /api/v1/health
│   └── stats.py            # GET /api/v1/stats
├── ws/
│   ├── __init__.py
│   └── live.py             # WS /api/v1/live (FULL_STATE + DIFFERENTIAL_UPDATE)
└── models/
    ├── __init__.py
    └── schemas.py          # Pydantic request/response models
```

---

## 2. Design Summary

The API is the single interface between the database and all consumers — the React frontend, external scripts, and the planned data science interface. It exposes both historical query endpoints and a real-time WebSocket feed.

Key capabilities:

- In-memory live aircraft cache updated via `LISTEN new_positions` (no polling)
- WebSocket endpoint: `FULL_STATE` on connect, `DIFFERENTIAL_UPDATE` every second
- REST endpoints for flight session queries with PostGIS trajectory GeoJSON
- REST endpoints for reference geometry (airports, runways, airspace, POIs)
- REST endpoints for pipeline configuration with hot-reload via DB trigger
- System health and operational statistics endpoints
- OpenAPI/Swagger documentation auto-generated at `/docs`

---

## 3. Endpoint Inventory

| Method | Path | Source | Description |
|--------|------|--------|-------------|
| `GET` | `/api/v1/health` | Postgres + TCP | API, DB, ingest, and ultrafeeder health |
| `GET` | `/api/v1/aircraft` | Live cache | All currently tracked aircraft |
| `GET` | `/api/v1/flights` | Postgres | Paginated session list (`?limit=&offset=`) |
| `GET` | `/api/v1/flights/{id}` | Postgres | Session detail with trajectory GeoJSON |
| `GET` | `/api/v1/stats` | Postgres + cache | Active aircraft, flights today, ingest rate, materializer lag |
| `GET` | `/api/v1/airspace` | Postgres | Airports, boundaries, POIs as GeoJSON |
| `GET` | `/api/v1/config` | Postgres | All `pipeline_config` entries |
| `PATCH` | `/api/v1/config/{key}` | Postgres | Update a config value (triggers `config_changed` NOTIFY) |
| `WS` | `/api/v1/live` | Live cache | Live aircraft WebSocket stream |

---

## 4. WebSocket Protocol

On connect, the client receives one `FULL_STATE` frame:

```json
{
  "type": "FULL_STATE",
  "timestamp": 1773712200.0,
  "aircraft": {
    "a12345": { "hex": "a12345", "lat": 39.995, "lon": -82.890, ... }
  }
}
```

Every subsequent second, the client receives a `DIFFERENTIAL_UPDATE`:

```json
{
  "type": "DIFFERENTIAL_UPDATE",
  "timestamp": 1773712201.0,
  "updates": { "a12345": { "lat": 39.996, "lon": -82.884, ... } },
  "removals": ["ab12cd"]
}
```

---

## 5. Running

```bash
POSTGRES_USER=planegraph POSTGRES_PASSWORD=... POSTGRES_DB=planegraph \
  uvicorn services.api.main:app --host 0.0.0.0 --port 8000
```

---

## 6. Related

| Document | Relationship |
|----------|--------------|
| [Services](../README.md) | Parent directory |
| [Data Dictionary](../../docs/reference/data-dictionary.md) | Schema queried |
| [Configuration Keys](../../docs/reference/configuration-keys.md) | Config endpoints serve these |
| [Docker Services](../../docs/reference/docker-services.md) | Will be added as a service |
