<!--
---
title: "Tagging Strategy Guide"
description: "Controlled vocabulary for document classification in Planegraph"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.1"
status: "Active"
tags:
  - type: guide
  - domain: documentation
related_documents:
  - "[Interior README Template](interior-readme-template.md)"
  - "[General KB Template](general-kb-template.md)"
---
-->

# Tagging Strategy Guide

## 1. Purpose

This guide defines the controlled tag vocabulary for the Planegraph project. Consistent tagging enables human navigation and RAG system retrieval across all project documentation.

---

## 2. Why Controlled Vocabulary

Uncontrolled tagging leads to:

- Synonyms fragmenting search (`database` vs `db` vs `databases`)
- Inconsistent granularity (`postgres` vs `relational-database`)
- Tag proliferation that reduces signal

A controlled vocabulary defines allowed values upfront, ensuring consistency across contributors and time.

---

## 3. Tag Categories

| Category | Question Answered | Example Values |
|----------|-------------------|----------------|
| `type` | What kind of document is this? | `guide`, `reference`, `specification`, `directory-readme` |
| `domain` | What subject area? | `reception`, `ingest`, `materialization`, `api`, `frontend` |
| `status` | What's the lifecycle state? | `draft`, `active`, `deprecated`, `archived` |
| `tech` | What technologies involved? | `postgres`, `docker`, `python`, `fastapi` |
| `audience` | Who is this for? | `beginners`, `intermediate`, `advanced`, `all` |

---

## 4. Domain Tags (Planegraph-Specific)

| Tag | Description |
|-----|-------------|
| `reception` | SDR hardware, antenna, ultrafeeder, dump978, signal chain |
| `ingest` | SBS parsing, real-time data pipeline from readsb to Postgres |
| `materialization` | Scheduled pipeline that promotes raw data into derived metrics, session summaries, and flight statistics |
| `schema` | Database schema design, PostGIS, migrations |
| `api` | FastAPI endpoints, REST interface, WebSocket live feed |
| `frontend` | React SPA, MapLibre GL, Deck.gl, dashboards, configuration UI |
| `monitoring` | Prometheus, Grafana, station health, system metrics |
| `deployment` | Docker Compose, edge box setup, backup, systemd services |
| `data-science` | Analysis patterns, query examples, research methodology |
| `documentation` | Templates, standards, tagging, meta-documentation |

---

## 5. Type Tags

| Tag | Use For |
|-----|---------|
| `directory-readme` | README for a directory (interior READMEs) |
| `project-root` | Repository root README |
| `guide` | Step-by-step procedures |
| `reference` | Lookup information (data dictionary, schema, API docs) |
| `specification` | Formal requirements or design documents |
| `worklog` | Work log milestone documentation |
| `report` | Analysis, findings, summaries |

---

## 6. Tech Tags

Canonical technology names used across the project:

| Tag | Refers To |
|-----|-----------|
| `postgres` | PostgreSQL 16 |
| `postgis` | PostGIS spatial extension |
| `docker` | Docker and Docker Compose |
| `python` | Python 3.11+ |
| `fastapi` | FastAPI web framework |
| `nginx` | nginx reverse proxy |
| `react` | React 18 SPA framework |
| `maplibre` | MapLibre GL JS map rendering |
| `deckgl` | Deck.gl WebGL overlay layers |
| `pmtiles` | PMTiles self-hosted vector tiles |
| `websocket` | WebSocket live data protocol |
| `readsb` | ADS-B decoder (inside ultrafeeder) |
| `tar1090` | ADS-B web visualization |
| `rtl-sdr` | RTL-SDR USB dongles |
| `prometheus` | Prometheus metrics |
| `grafana` | Grafana dashboards |

---

## 7. Status Tags

| Tag | Description |
|-----|-------------|
| `draft` | In development, not yet complete |
| `active` | Current, maintained |
| `deprecated` | Superseded, avoid for new work |
| `archived` | Historical reference only |

---

## 8. Implementation

### In YAML Frontmatter

```yaml
<!--
---
title: "Document Title"
description: "What this document covers"
author: "VintageDon (https://github.com/vintagedon)"
tags:
  - type: guide
  - domain: ingest
  - tech: [python, postgres]
  - status: active
  - audience: intermediate
---
-->
```

### Conventions

- Use lowercase, hyphenated values (`materialization` not `Materialization`)
- Tech tags use canonical names from section 6
- One value per line for readability, or array syntax for multi-value
- Author always includes GitHub profile link

---

## 9. Maintaining the Vocabulary

### Adding New Tags

1. Check if existing tag covers the concept
2. If not, propose new tag with definition
3. Update this document
4. Backfill existing documents if needed

### Governance

- Keep vocabulary in version control (this file)
- Review additions for overlap with existing tags
- Prefer broader tags over proliferating specific ones

---

## 10. References

| Resource | Description |
|----------|-------------|
| [Interior README Template](interior-readme-template.md) | Shows tag usage in frontmatter |
| [General KB Template](general-kb-template.md) | Shows tag usage for standalone docs |
| [Planegraph Repository](https://github.com/radioastronomyio/planegraph-aviation-tracker) | Project home |
