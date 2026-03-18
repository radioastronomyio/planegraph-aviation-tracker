<!--
---
title: "Docker Services"
description: "Container definitions, ports, volumes, and health checks"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: reference
  - domain: deployment
  - tech: [docker, postgres, postgis, readsb]
  - audience: intermediate
related_documents:
  - "[Data Dictionary](data-dictionary.md)"
  - "[Application Stack Guide](../deployment/04-application-stack.md)"
---
-->

# Docker Services

Reference for all Docker Compose services defined in `docker/docker-compose.yml`. Each service entry covers its image, ports, volumes, environment variables, health checks, and operational notes.

---

## 1. Stack Overview

The Planegraph stack uses a single `docker-compose.yml` with a named project (`planegraph`) and a dedicated bridge network (`planegraph-net`). All services restart automatically unless explicitly stopped.

```
docker/docker-compose.yml
├── planegraph-postgres      # PostGIS database
├── planegraph-ultrafeeder   # ADS-B receiver + decoder
└── [future services added by WU-03+]
```

---

## 2. planegraph-postgres

| Property | Value |
|----------|-------|
| Image | `postgis/postgis:16-3.4-alpine` |
| Container Name | `planegraph-postgres` |
| Restart Policy | `unless-stopped` |

### Ports

| Host | Container | Protocol | Purpose |
|------|-----------|----------|---------|
| 5432 | 5432 | TCP | PostgreSQL client connections |

### Volumes

| Host Path | Container Path | Mode | Purpose |
|-----------|---------------|------|---------|
| `postgres_data` (named volume) | `/var/lib/postgresql/data` | rw | Persistent database storage |
| `./postgres/postgresql.conf` | `/etc/postgresql/postgresql.conf` | ro | Custom Postgres configuration |
| `./postgres/init/` | `/docker-entrypoint-initdb.d/` | ro | Extension initialization scripts |

### Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `POSTGRES_DB` | `.env` | Database name (default: `planegraph`) |
| `POSTGRES_USER` | `.env` | Database user (default: `planegraph`) |
| `POSTGRES_PASSWORD` | `.env` | Database password (must be changed from template) |
| `PGDATA` | `.env` | Data directory inside container |

### Health Check

```yaml
test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER:-planegraph}"]
interval: 10s
timeout: 5s
retries: 5
start_period: 20s
```

The `start_period` gives PostgreSQL 20 seconds to initialize on first boot (including running init scripts in `/docker-entrypoint-initdb.d/`) before health checks begin counting failures.

### Configuration

The container uses a custom `postgresql.conf` tuned for write-heavy ADS-B workloads. Key settings include `synchronous_commit = off` (trading durability for throughput on position reports), `wal_level = minimal` (no replication), and aggressive checkpoint settings for sustained sequential writes. Full configuration is in `docker/postgres/postgresql.conf`.

### Operational Notes

The named volume `postgres_data` persists database files across container restarts and image upgrades. To reset the database completely: `docker compose down -v` (destroys the volume), then `docker compose up -d` and re-run migrations.

---

## 3. planegraph-ultrafeeder

| Property | Value |
|----------|-------|
| Image | `ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder:latest` |
| Container Name | `planegraph-ultrafeeder` |
| Restart Policy | `unless-stopped` |
| Privileged | `true` (required for USB device access) |

### Ports

| Host | Container | Protocol | Purpose |
|------|-----------|----------|---------|
| 8080 | 80 | TCP | tar1090 web UI (live map and stats) |
| 30003 | 30003 | TCP | SBS/BaseStation output (decoded ADS-B as CSV-like text) |
| 30005 | 30005 | TCP | Beast binary output (decoded ADS-B as binary frames) |

### Volumes

| Host Path | Container Path | Mode | Purpose |
|-----------|---------------|------|---------|
| `/dev/bus/usb` | `/dev/bus/usb` | rw | USB device passthrough for SDR dongles |

### Environment Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `READSB_DEVICE_TYPE` | `.env` | SDR device type (`rtlsdr`) |
| `READSB_RTLSDR_DEVICE` | `.env` | Device index (`0` for first dongle) |
| `READSB_LAT` | `.env` | Receiver latitude (decimal degrees) |
| `READSB_LON` | `.env` | Receiver longitude (decimal degrees) |
| `READSB_ALT` | `.env` | Receiver altitude (meters MSL, appended with `m`) |
| `READSB_GAIN` | `.env` | SDR gain setting (`autogain` recommended) |
| `READSB_NET_SBS_OUTPUT_PORT` | `.env` | SBS output port (default: `30003`) |
| `READSB_NET_BEAST_OUTPUT_PORT` | `.env` | Beast output port (default: `30005`) |
| `UPDATE_TAR1090` | `.env` | Auto-update tar1090 web UI (`true`) |
| `TAR1090_DEFAULTCENTERLAT` | `.env` | Default map center latitude |
| `TAR1090_DEFAULTCENTERLON` | `.env` | Default map center longitude |

### Privileged Mode

The `privileged: true` flag is required because readsb needs direct access to the RTL-SDR USB devices via `/dev/bus/usb`. This is the standard deployment pattern for SDR containers. The security implications are documented and accepted in the [CIS compliance matrix](../security/cis-v8-ig1-baseline.md) (Control 4.6).

### Operational Notes

The tar1090 web UI at `http://<host>:8080` provides a live aircraft map, signal statistics, and reception range plots. This UI is for validation and debugging — the production frontend is the React application (WU-04+).

The SBS output on port 30003 is the primary data feed consumed by the ingest daemon (WU-02). Each line is a comma-separated decoded ADS-B message. The Beast output on port 30005 is available for tools that prefer binary protocol but is not used by the Planegraph ingest pipeline.

Ultrafeeder auto-updates its internal tar1090 installation when `UPDATE_TAR1090=true`. The container image itself should be updated periodically with `docker compose pull planegraph-ultrafeeder && docker compose up -d`.

---

## 4. Network

All services connect to the `planegraph-net` bridge network, enabling inter-container communication by container name. Services can reach each other as `planegraph-postgres:5432` or `planegraph-ultrafeeder:30003` from within the Docker network.

---

## 5. Common Operations

### Start the stack

```bash
docker compose -f docker/docker-compose.yml up -d
```

### Stop the stack

```bash
docker compose -f docker/docker-compose.yml down
```

### View logs

```bash
# All services
docker compose -f docker/docker-compose.yml logs -f

# Single service
docker compose -f docker/docker-compose.yml logs -f planegraph-postgres
```

### Update container images

```bash
docker compose -f docker/docker-compose.yml pull
docker compose -f docker/docker-compose.yml up -d
```

### Reset database (destructive)

```bash
docker compose -f docker/docker-compose.yml down -v
docker compose -f docker/docker-compose.yml up -d
# Wait for health check, then re-run migrations
bash migrations/run.sh
```

---

## 6. References

| Resource | Description |
|----------|-------------|
| [docker-compose.yml](../../docker/docker-compose.yml) | Source Compose file |
| [postgresql.conf](../../docker/postgres/postgresql.conf) | Postgres configuration |
| [.env.example](../../docker/.env.example) | Environment variable template |
| [ultrafeeder docs](https://github.com/sdr-enthusiasts/docker-adsb-ultrafeeder) | Upstream container documentation |

---

## 7. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
