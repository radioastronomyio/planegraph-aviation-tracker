<!--
---
title: "Docker"
description: "Docker Compose stack, container configuration, and environment setup"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: deployment
  - tech: [docker, postgres, postgis, readsb]
---
-->

# Docker

Docker Compose stack and container configuration for the Planegraph platform. All services run on a single edge box (Intel N100).

---

## 1. Contents

```
docker/
├── docker-compose.yml      # Service definitions (postgres, ultrafeeder)
├── .env.example            # Environment variable template
├── postgres/
│   ├── postgresql.conf     # Write-heavy tuned Postgres config
│   └── init/
│       └── 00-extensions.sql   # PostGIS extension initialization
├── nginx/
│   └── README.md           # Placeholder for WU-07
└── README.md               # This file
```

---

## 2. Services

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| `planegraph-postgres` | `postgis/postgis:16-3.4-alpine` | 5432 | PostGIS database for all application data |
| `planegraph-ultrafeeder` | `ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder:latest` | 8080, 30003, 30005 | 1090 MHz ADS-B reception, decoding, and SBS output |

---

## 3. Usage

Copy the environment template and set a real password before first run:

```bash
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD and receiver coordinates
docker compose up -d
```

Run migrations after containers are healthy:

```bash
bash migrations/run.sh
```

---

## 4. Related

| Document | Relationship |
|----------|--------------|
| [Repository Root](../README.md) | Parent directory |
| [Migrations](../migrations/README.md) | SQL schema and seed data |
| [nginx/](nginx/README.md) | Reverse proxy config (WU-07) |
