# Agent Instructions

This file is the single source of project context for AI agents. Load it fully before starting work.

---

## Project Identity

**Planegraph** is a self-hosted aviation data platform for ADS-B aircraft surveillance. It receives, decodes, stores, materializes, and serves aviation data from a local SDR receiver station. The system runs entirely on a low-power edge box and exposes both a data science API and a web-based dashboard with live map visualization.

## Domain Context

ADS-B (Automatic Dependent Surveillance-Broadcast) is a surveillance technology where aircraft broadcast their position, altitude, speed, and identity on 1090 MHz. In the US, UAT (Universal Access Transceiver) operates on 978 MHz for aircraft below 18,000 feet. This project receives both 1090 MHz and 978 MHz using two RTL-SDR dongles with a dual-channel SAWbird+ LNA.

Key domain terminology:

- **hex** — ICAO 24-bit aircraft address (unique identifier, e.g., `a12345`)
- **squawk** — 4-digit transponder code assigned by ATC
- **Mode S** — the surveillance protocol that ADS-B extends
- **readsb** — the actively maintained ADS-B decoder (fork of dump1090)
- **tar1090** — web-based ADS-B visualization interface
- **SBS/BaseStation** — CSV-like text protocol for decoded ADS-B messages (port 30003)
- **Beast** — binary protocol for decoded ADS-B messages (port 30005)

## Architecture Overview

### Hardware

- **Edge box**: ACEMAGICIAN N100 (4C/4T, 12GB LPDDR5, 256GB M.2 SSD, dual GbE)
- **OS**: Ubuntu 24.04, 15W turbo mode
- **SDR**: 2x Nooelec RTL-SDR v5 (device 0: 1090 MHz, device 1: 978 MHz)
- **LNA**: Nooelec SAWbird+ ADS-B (dual-channel, ~35dB gain, <0.9dB NF)
- **Antenna**: 2x Dual-band 1090/978 MHz fiberglass, 5dBi
- **Enclosure**: CHENGPI IP65 steel box with thermostat fan
- **Power**: Shanqiu mini UPS (74Wh, 12V DC direct to N100, 5V for LNA)
- **Network**: WiFi to home AP

### Software Stack

| Layer | Component | Purpose |
|-------|-----------|---------|
| Reception | ultrafeeder (Docker) | readsb + tar1090 for 1090 MHz ADS-B |
| Storage | PostgreSQL 16 + PostGIS | Partitioned position reports, flight sessions, reference geometry |
| Ingest | Python asyncio daemon | SBS stream consumer, session management, batch writer |
| Materialization | Python scheduler | Flight metric computation, partition management, retention |
| API | FastAPI | REST endpoints + WebSocket live aircraft feed |
| Frontend | React + MapLibre GL + Deck.gl | Live map, dashboards, configuration, data science views |
| Tiles | PMTiles | Self-hosted vector base map |
| Proxy | nginx | Reverse proxy, SPA routing, tile serving |

### Data Flow

```
Antenna → SAWbird+ LNA (5V from UPS) → RTL-SDR v5 (USB)
  → ultrafeeder container (readsb decoder)
    → tar1090 web UI (live map, validation only)
    → SBS output port 30003
    → aggregator feeds (ADS-B Exchange, FlightAware, etc.)

SBS port 30003 → Python ingest daemon → PostgreSQL (position_reports)
  → Session segmentation → Flight materialization → Derived metrics
  → FastAPI (REST + WebSocket) → React SPA (MapLibre + Deck.gl)
```

### Key Upstream Projects

- [sdr-enthusiasts/docker-adsb-ultrafeeder](https://github.com/sdr-enthusiasts/docker-adsb-ultrafeeder) — All-in-one ADS-B container
- [bellingcat/adsb-history](https://github.com/bellingcat/adsb-history) — Turnstone: PostGIS schema reference
- [wiedehopf/tar1090-db](https://github.com/wiedehopf/tar1090-db) — Aircraft metadata database

### Columbus Coverage Area

The receiver covers four airports with reference geometry seeded in the database:

| Airport | ICAO | Type |
|---------|------|------|
| John Glenn Columbus International | KCMH | Class C, commercial hub |
| Rickenbacker International | KLCK | Military/cargo |
| Ohio State University Airport | KOSU | GA, training |
| Bolton Field | KTZR | GA |

Reference data includes 16 runway thresholds with 15 NM extended centerlines, 5 airspace boundaries (KCMH Class C surface + shelf, 3x Class D), and 16 points of interest (approach fixes, navaids, overflight zones).

### Work Unit Structure

The project is implemented in seven sequential work units:

| WU | Name | Status |
|----|------|--------|
| 01 | Infrastructure & Data Foundation | ✅ Complete |
| 02 | Ingest Pipeline & Materialization | ✅ Complete |
| 03 | API Layer | ✅ Complete |
| 04 | Frontend Foundation | ✅ Complete |
| 05 | Dashboard & Configuration UI | Next |
| 06 | Data Science & Visualization | Planned |
| 07 | Integration & Polish | Planned |

Specifications for each work unit are in `spec/wu-NN-*/README.md` (not committed to the public repo).

## Coding Conventions

- Python 3.11+ for all services
- Type hints required
- NumPy-style docstrings
- Docker Compose for all containerized services
- SQL migrations versioned in `migrations/`, numbered sequentially
- Configuration via `.env` files (not committed) with `.env.example` templates
- Follow existing patterns in surrounding files
- Documentation follows templates in `docs/documentation-standards/`
- YAML frontmatter on all markdown files
- See `docs/documentation-standards/tagging-strategy.md` for tag vocabulary

## Repository Layout

```
planegraph-aviation-tracker/
├── docker/                     # Docker Compose, Postgres config, env
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── postgres/               # postgresql.conf, init scripts
│   └── nginx/                  # Reverse proxy (WU-07)
├── migrations/                 # Numbered SQL migrations + runner
├── services/                   # Application services
│   ├── ingest/                 # SBS consumer daemon (WU-02)
│   ├── materializer/           # Scheduled materialization (WU-02)
│   └── api/                    # FastAPI application (WU-03)
├── frontend/                   # React SPA (WU-04)
├── docs/                       # Documentation and standards
├── internal-files/             # GDR research outputs (gitignored)
├── shared/                     # Cross-project utilities
├── AGENTS.md                   # This file
├── WORKLOG.md                  # Session-by-session progress
├── LICENSE                     # MIT (code)
└── LICENSE-DATA                # CC-BY-4.0 (data products)
```
