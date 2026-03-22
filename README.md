<!--
---
title: "Planegraph"
description: "Self-hosted aviation data platform for ADS-B aircraft surveillance"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-21"
version: "0.5"
status: "Active"
tags:
  - type: project-root
  - domain: [aviation, data-science, ADS-B, SDR]
  - tech: [postgres, postgis, python, docker, fastapi, react, maplibre, deckgl, rtl-sdr]
related_documents:
  - "[SDR Enthusiasts Ultrafeeder](https://github.com/sdr-enthusiasts/docker-adsb-ultrafeeder)"
  - "[Bellingcat Turnstone](https://github.com/bellingcat/adsb-history)"
---
-->

# ✈️ Planegraph

[![ADS-B](https://img.shields.io/badge/Domain-Aviation_Data-green)]()
[![Stack](https://img.shields.io/badge/Stack-PostGIS_+_FastAPI_+_React-blue)]()
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)


![alt text](assets/repo-banner.jpg)
> A self-hosted aviation data platform that receives, decodes, segments, and serves ADS-B aircraft surveillance data through a web UI with live map visualization and data science capabilities — all on a single edge box.

Planegraph treats ADS-B data as a first-class dataset rather than a live-map-and-forget exercise. Every position report flows through a materialization pipeline that segments flights, classifies phases, computes derived metrics, and serves the results through a React dashboard with MapLibre GL mapping and Deck.gl overlays. The system enables queries that no existing open-source ADS-B tool supports — approach deviation analysis, traffic pattern heatmaps, fleet composition trends, and trajectory replay.

---

## 🔭 Overview

Most open-source ADS-B setups stop at reception and visualization: decode the signal, show planes on a map, feed aggregators. The historical data either gets thrown away or archived in flat files that nobody touches.

Planegraph builds a progressively enriched data product. Raw position reports are ingested in real-time, segmented into flight sessions using configurable gap thresholds, classified through fuzzy phase detection (ground, takeoff, climb, cruise, descent, approach, landing), and materialized into derived metrics. The Columbus, Ohio area serves as the primary coverage zone, with reference geometry for KCMH, KLCK, KOSU, and KTZR airports including runway centerlines, airspace boundaries, and points of interest.

The entire system runs on a low-power edge box (Intel N100, 12GB RAM, 256GB SSD) deployed outdoors with battery backup, receiving 1090 MHz ADS-B and 978 MHz UAT.

---

## 📊 Project Status

| Area | Status | Description |
|------|--------|-------------|
| Hardware | ✅ Acquired | All components purchased and available |
| Infrastructure (WU-01) | ✅ Complete | Docker Compose, PostgreSQL/PostGIS, ultrafeeder, schema, seed data |
| Ingest Pipeline (WU-02) | ✅ Complete | Python asyncio SBS consumer, session manager, phase classifier, batch writer, materializer |
| API Layer (WU-03) | ✅ Complete | FastAPI REST + WebSocket live feed, in-memory aircraft cache, config PATCH |
| Frontend (WU-04) | ✅ Complete | React SPA, MapLibre GL, Deck.gl aircraft layers |
| Dashboard & Config (WU-05) | ⬜ Next | Statistics panels, configuration UI, system health |
| Data Science & Viz (WU-06) | ⬜ Planned | Trajectory replay, approach analysis, heatmaps |
| Integration (WU-07) | ⬜ Planned | nginx, systemd, end-to-end testing, documentation |

---

## 🏗️ Architecture

### Data Flow

![alt text](assets/data-flow-section-infographic.jpg)

### Software Stack

| Layer | Component | Purpose |
|-------|-----------|---------|
| Reception | ultrafeeder (Docker) | readsb + tar1090 for 1090 MHz ADS-B decoding |
| Storage | PostgreSQL 16 + PostGIS | Partitioned position reports, flight sessions, reference geometry |
| Ingest | Python asyncio daemon | SBS stream consumer, session management, batch writer |
| Materialization | Python scheduler | Flight metric computation, partition management, retention |
| API | FastAPI | REST endpoints + WebSocket live aircraft feed |
| Frontend | React + MapLibre GL + Deck.gl | Live map, dashboards, configuration, data science views |
| Tiles | PMTiles | Self-hosted vector base map tiles |
| Proxy | nginx | Reverse proxy, SPA routing, tile serving |

### Hardware

| Component | Model | Role |
|-----------|-------|------|
| Edge Computer | ACEMAGICIAN N100 (4C/4T, 12GB LPDDR5, 256GB SSD) | Runs entire stack |
| SDR Dongle | Nooelec RTL-SDR v5 | 1090 MHz reception |
| LNA | Nooelec SAWbird+ ADS-B | Dual-channel, ~35dB gain, <0.9dB NF |
| Antenna | Dual-band 1090/978 MHz fiberglass, 5dBi | Signal capture |
| Enclosure | CHENGPI IP65 steel box w/ thermostat fan | Outdoor deployment |
| UPS | Shanqiu 74Wh mini UPS (12V DC + 5V) | Powers N100 + LNA directly |

---

## 📁 Repository Structure

```
planegraph-aviation-tracker/
├── 📂 docker/                      # Docker Compose, Postgres config, env
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── postgres/                   # postgresql.conf, init scripts
│   └── nginx/                      # Reverse proxy (WU-07)
├── 📂 migrations/                  # Numbered SQL migrations + runner
├── 📂 services/                    # Application services
│   ├── ingest/                     # SBS consumer daemon (WU-02)
│   ├── materializer/               # Scheduled materialization (WU-02)
│   └── api/                        # FastAPI application (WU-03)
├── 📂 frontend/                    # React SPA (WU-04)
├── 📂 docs/                        # Full project documentation
│   ├── hardware/                   # BOM, signal chain, physical build
│   ├── deployment/                 # Step-by-step from OS to running stack
│   ├── security/                   # CIS v8 IG1 compliance baseline
│   ├── reference/                  # Data dictionary, config keys, services
│   ├── operations/                 # Backup, recovery, troubleshooting
│   └── documentation-standards/    # Template library and tagging strategy
├── 📂 internal-files/              # GDR research outputs (gitignored)
├── 📂 shared/                      # Cross-project utilities
├── 📄 AGENTS.md                    # Agent instructions + project context
├── 📄 WORKLOG.md                   # Session-by-session progress
├── 📄 LICENSE                      # MIT (code)
├── 📄 LICENSE-DATA                 # CC-BY-4.0 (data products)
└── 📄 README.md                    # This file
```

---

## 📚 Documentation

The `docs/` directory provides complete build-to-operate documentation. For a new deployment, follow the [reading order](docs/README.md) from hardware through verification. Key sections:

- [Hardware BOM](docs/hardware/bill-of-materials.md) — Full parts list with costs and alternatives
- [Deployment Guide](docs/deployment/README.md) — OS install → hardening → SDR → stack → verification
- [Security Baseline](docs/security/cis-v8-ig1-baseline.md) — CIS v8 IG1 compliance matrix
- [Data Dictionary](docs/reference/data-dictionary.md) — Every table and column documented
- [Operations](docs/operations/README.md) — Backup, recovery, troubleshooting

---

## 🌐 Public-Facing Plans

- **Domain**: columbusaviation.dev (available)
- **Social**: @columbusaviation (available)
- **Goal**: Public aviation stats for Columbus, OH area (CMH, OSU, Bolton, LCK) with data science query capabilities
- **Model**: Configurable API key for AI-powered natural language queries against the dataset

---

## 🔬 Upstream & Influences

| Project | Relationship |
|---------|-------------|
| [sdr-enthusiasts/ultrafeeder](https://github.com/sdr-enthusiasts/docker-adsb-ultrafeeder) | Reception layer — off-the-shelf Docker for ADS-B decoding |
| [bellingcat/adsb-history](https://github.com/bellingcat/adsb-history) | Schema reference — Turnstone's PostGIS schema for historical ADS-B |
| [wiedehopf/tar1090-db](https://github.com/wiedehopf/tar1090-db) | Aircraft metadata database |

---

## 🌟 Open Science Philosophy

We practice open science and open methodology — our version of "showing your work":

- Research methodologies are fully documented and repeatable
- Infrastructure configurations are version-controlled and automated
- Scripts and pipelines are published so others can learn, adapt, or improve them
- Learning processes are captured and shared for community benefit

All projects operate under open source licenses (primarily MIT) to ensure maximum reproducibility.

---

## 📄 License

- **Code**: [MIT License](LICENSE)
- **Data Products**: [CC-BY-4.0](LICENSE-DATA)

---

Last Updated: March 21, 2026 | Status: WU-04 Complete, WU-05 Next
