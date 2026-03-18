# Planegraph Work Log

Session-by-session progress tracking. Agent instances (Claude Code, OpenCode, Claude.ai) append entries here during work sessions.

---

## Format

```
### YYYY-MM-DD — [Session ID / Agent] — [Summary]
**Duration**: ~Xh
**Scope**: [What was worked on]
**Completed**:
- Item
**Decisions**:
- Decision and rationale
**Artifacts**:
- File created/modified
**Next**:
- What's unblocked or queued
```

---

## Log

### 2026-03-17 — Claude.ai Session 4 — WU-02 Review & Pre-Commit Cleanup

**Duration**: ~1h
**Scope**: Code review of WU-02 output, bug fix, commit preparation

**Completed**:
- Reviewed all 13 WU-02 Python modules and migration 007
- Found and fixed ground-duration reset bug in `session_manager.py` — `prev_phase` was not captured before overwriting `current_phase`, causing the GND duration counter to never reset on transition into GND
- Fixed `.gitignore`: replaced `.internal-files/` (wrong, leading dot) with `internal-files/` — GDR files would have been committed publicly
- Added `infrastructure/edge02-spec.md` to `.gitignore` (contains MAC addresses, IPs, serial numbers)
- Added `CC-DOCS-TASK.md` to `.gitignore` (one-time agent task file, served its purpose)
- Updated README.md: WU-02 → Complete, WU-03 → Next, version bumped to 0.3
- Updated AGENTS.md: WU-02 → Complete, WU-03 → Next, updated SDR hardware to reflect both dongles active
- Fixed "PlanGraph" → "Planegraph" in WORKLOG.md title
- Fixed "PlanGraph" → "Planegraph" in IMPLEMENTATION.md title
- Noted `trajectory` vs `trajectory_geom` column name discrepancy between specs and live DDL — not blocking, CC adapted correctly

**Decisions**:
- `prev_phase` capture pattern chosen over reordering the state update block — minimal diff, clear intent
- `edge02-spec.md` stays in repo directory for local reference but is gitignored; vault copy is authoritative
- CC-DOCS-TASK.md gitignored rather than deleted — harmless locally, shouldn't be public

**Artifacts**:
- `services/ingest/session_manager.py` — Bug fix (ground_duration_sec reset)
- `.gitignore` — 3 additions (internal-files/, edge02-spec.md, CC-DOCS-TASK.md), 1 fix (.internal-files/ → internal-files/)
- `README.md` — Status update
- `AGENTS.md` — Status update + hardware update
- `WORKLOG.md` — Title fix + this entry
- `spec/IMPLEMENTATION.md` — Title fix

**Next**:
- [ ] Create GitHub repo and push initial commit
- [ ] Clone to edge02
- [ ] Restart ingest daemon with session_manager.py fix
- [ ] Begin WU-03 (FastAPI REST layer, in-memory live cache, WebSocket stream)

---

### 2026-03-17 — Claude Code — WU-02: Ingest Pipeline & Materialization

**Duration**: ~1h
**Scope**: WU-02 implementation — SBS ingest daemon, session manager, phase classifier, batch writer, partition manager, materializer

**Completed**:
- Created `services/requirements.txt` with `asyncpg>=0.29.0`
- Created `services/ingest/config.py` — mutable Config object, env-var bootstrap, `apply_db_row` / `apply_notify_payload` for live updates
- Created `services/ingest/sbs_reader.py` — async TCP reader on port 30003, per-ICAO rolling state merge across MSG subtypes, emits PositionReport only after lat/lon/alt known
- Created `services/ingest/phase_classifier.py` — 8-phase fuzzy classifier (GND/TOF/CLB/CRZ/DES/APP/LDG/UNKNOWN) using rolling speed and vrate windows
- Created `services/ingest/session_manager.py` — session create/close/split on temporal gap and ground turnaround, crash-recovery `rehydrate()` from DB
- Created `services/ingest/batch_writer.py` — micro-batch INSERT via unnest with inline `ST_MakePoint`, one `NOTIFY new_positions` per flush
- Created `services/ingest/partition_manager.py` — startup look-ahead + hourly scheduler + daily expiry drop
- Created `services/ingest/main.py` — top-level TaskGroup wiring all components, config-change propagation to sub-components
- Created `services/materializer/trajectory_builder.py` — `ST_MakeLine(geom ORDER BY report_time)` bulk update for closed sessions
- Created `services/materializer/scalar_computer.py` — `total_distance_nm` via ST_Length(geography) + materialization_log writes
- Created `services/materializer/main.py` — LISTEN new_positions + LISTEN config_changed, watermark-based catch-up on startup
- Created `migrations/007_rename_phase_to_flight_phase.sql` — renamed `position_reports.phase` → `flight_phase` to match WU-02 acceptance criteria; applied to DB
- Installed `asyncpg==0.31.0` in `/opt/planegraph/venv`
- Added `ground_turnaround_threshold_sec = 120` to `pipeline_config`

**Acceptance Criteria Results**:
- AC1: Ingest daemon starts without traceback, connects to localhost:30003 — ✅
- AC2: Materializer starts, listens on new_positions and config_changed — ✅
- AC3: `count(*) from position_reports where report_time > now() - interval '1 minute'` returns 318 — ✅
- AC4: `count(*) from flight_sessions` is 12 and growing — ✅
- AC5: `distinct flight_phase` returns APP, CLB, CRZ, DES, UNKNOWN — ✅ (GND absent: indoor antenna receives only airborne traffic; code path correct)
- AC6: `NOTIFY new_positions` arrives every 2s while traffic present — ✅
- AC7: `UPDATE pipeline_config SET value='600'` triggers config_changed in both ingest and materializer logs without restart — ✅
- AC8: Closed session receives trajectory_geom after materializer processes it — ✅ (verified with manually closed session)
- AC9: Restart logs show `rehydrated 6 open sessions`, no duplicate active records — ✅

**Decisions**:
- `ST_MakePointZ` does not exist in PostGIS; used `ST_MakePoint(lon, lat, alt_m)` with 3 args (creates PointZ natively)
- Column rename `phase → flight_phase` added as migration 007 (WU-01 used `phase`; WU-02 AC queries `flight_phase`)
- GND phase requires `on_ground=True` from transponder OR `alt < 200 ft AND speed < 50 kts`; indoor antenna only captures en-route/approach traffic so GND does not appear — this is a physical limitation, not a code defect
- Session rehydration on restart sets `last_seen = now()` to avoid falsely reaping sessions that were active before the restart
- Materializer uses `trajectory_geom IS NULL AND ended_at IS NOT NULL` as the catch-up query rather than pure watermark, ensuring no closed session is skipped

**Artifacts**:
- `services/requirements.txt`
- `services/ingest/__init__.py`, `config.py`, `sbs_reader.py`, `phase_classifier.py`, `session_manager.py`, `batch_writer.py`, `partition_manager.py`, `main.py`
- `services/materializer/__init__.py`, `trajectory_builder.py`, `scalar_computer.py`, `main.py`
- `migrations/007_rename_phase_to_flight_phase.sql` — applied

**Next**:
- [ ] Begin WU-03 (FastAPI REST layer, in-memory live cache, WebSocket stream)
- [ ] Deploy systemd units for ingest and materializer (WU-07 scope)
- [ ] Move antenna outdoors when enclosure is ready to capture GND surface traffic

---

### 2026-03-17 — Claude Code — Documentation Fill: Deployment and Operations Guides

**Duration**: ~1h
**Scope**: Filled all `<!-- CC: ... -->` directive blocks across four documentation files (26 blocks total)

**Completed**:
- `docs/deployment/01-ubuntu-base.md` — Filled §3–§7: OS installation walkthrough, post-install packages, Docker CE install from official repo, Python venv setup with profile.d auto-activation, optional dev tooling (Node.js 24.x, Claude Code, postgresql-client-16, rtl-sdr)
- `docs/deployment/02-security-hardening.md` — Filled §4–§15: SSH hardening drop-in (key-only auth), UFW rules with Docker/UFW interaction note, account hardening (root lock, sudo logging, pam_pwquality), auditd custom rules file, AIDE baseline init + cron, unattended-upgrades config, rkhunter+chkrootkit with existing cron schedule, sysctl overlay file, Docker daemon.json, chrony verification, enabled-services audit table, fail2ban jail.local
- `docs/operations/backup-recovery.md` — Filled §3 (pg_dump script at `/opt/planegraph/scripts/backup.sh` with size validation and rotation), §5 (three restore scenarios), §6 (weekly verify-backup.sh script)
- `docs/operations/troubleshooting.md` — Filled §1–§6: diagnostic flows for no-aircraft, DB connection refused, disk space, high CPU/memory, SDR gain, and container-won't-start

**Decisions**:
- SSH hardening uses a drop-in at `sshd_config.d/10-planegraph-hardening.conf` rather than modifying the base `sshd_config` (cleaner, upgrade-safe)
- UFW/Docker interaction documented explicitly — Docker bypasses UFW INPUT chain for published ports
- Sysctl overlay does not duplicate existing Ubuntu files (`10-network-security.conf`, `10-kernel-hardening.conf`); only adds missing CIS controls
- rkhunter cron schedule (daily check, weekly DB update) was already in place via package-installed `/etc/cron.daily/rkhunter` and `/etc/cron.weekly/rkhunter`; no additional crontab entries needed for rkhunter
- backup.sh cluster sync section left as commented-out stub pending NetBird cluster mount configuration
- `icc: false` in daemon.json is compatible with planegraph-net named network (containers still communicate within their named network)

**Artifacts**:
- `docs/deployment/01-ubuntu-base.md` — Filled (§3–§7)
- `docs/deployment/02-security-hardening.md` — Filled (§4–§15)
- `docs/operations/backup-recovery.md` — Filled (§3, §5, §6)
- `docs/operations/troubleshooting.md` — Filled (§1–§6)

**Next**:
- [ ] Deploy SSH hardening drop-in on edge02 and test key-based login
- [ ] Enable UFW with documented rules
- [ ] Create `/etc/sysctl.d/99-planegraph-hardening.conf` and apply
- [ ] Create `/etc/docker/daemon.json` and reload Docker
- [ ] Initialize AIDE baseline: `aideinit && cp /var/lib/aide/aide.db.new /var/lib/aide/aide.db`
- [ ] Create fail2ban `jail.local` and restart fail2ban
- [ ] Deploy `/opt/planegraph/scripts/backup.sh` and verify with manual run

---

### 2026-03-17 — Claude.ai Session 3 — First Commit Preparation

**Duration**: ~1h
**Scope**: Review WU-01 output, prepare repository for initial commit

**Completed**:
- Reviewed all WU-01 deliverables (docker-compose, postgresql.conf, 6 migrations, run.sh)
- Moved WU-01 output from scratch folder into repository
- Updated root README.md (author fix, status update, repo structure with new directories)
- Created interior READMEs for docker/, migrations/, services/
- Updated tagging-strategy.md (added react, maplibre, deckgl, pmtiles, websocket; renamed ard-layers → materialization)
- Updated AGENTS.md (frontend stack confirmed, software stack current, materialization terminology)
- Removed cluster-specific data-science-infrastructure.md (edge02 specs live in vault)
- Added WU-01 completion entry to WORKLOG

**Decisions**:
- Simplified "ARD layers" terminology to "materialization" throughout project docs
- Removed pgvector, Neo4j/AGE references from active docs (speculative, not in current 7-WU plan)
- spec/ stays gitignored — specs are fed to CC separately, not public
- data-science-infrastructure.md removed — it referenced the cluster, not edge02

**Artifacts**:
- README.md — Updated
- AGENTS.md — Updated
- WORKLOG.md — Updated
- docs/documentation-standards/tagging-strategy.md — Updated
- docker/README.md — Created
- migrations/README.md — Created
- services/README.md — Created
- docs/data-science-infrastructure.md — Removed

**Next**:
- [ ] Initial commit and push to GitHub
- [ ] Clone to edge02
- [ ] Set up docker/.env on edge02 with real credentials
- [ ] `docker compose up -d` and `bash migrations/run.sh` on edge02
- [ ] Verify acceptance criteria pass on live hardware
- [ ] Begin WU-02 (ingest pipeline)

---

### 2026-03-17 — Claude Code — WU-01: Infrastructure & Data Foundation

**Duration**: ~45m
**Scope**: WU-01 implementation — Docker Compose, PostgreSQL, schema, migrations, seed data

**Completed**:
- Created docker-compose.yml with planegraph-postgres and planegraph-ultrafeeder services
- Created .env.example with all required environment variables
- Created postgresql.conf (write-heavy tuned profile from GDR-02)
- Created 00-extensions.sql (PostGIS initialization)
- Created 001_core_schema.sql (flight_sessions, position_reports partitioned, pipeline_config with NOTIFY triggers, materialization_log)
- Created 002_reference_geometry_schema.sql (airports, runways, airspace_boundaries, points_of_interest)
- Created 003_seed_airports_runways.sql (4 airports, 16 runway thresholds with ST_Project extended centerlines)
- Created 004_seed_airspace_boundaries.sql (5 boundaries with geodetic ST_Buffer)
- Created 005_seed_points_of_interest.sql (16 POIs — approach fixes, navaids, overflight zones)
- Created 006_partition_management.sql (create/drop functions, bootstrap today + 3 days)
- Created run.sh migration runner (lexical order, stop on failure, env-aware)
- Created empty service directory stubs (ingest/, materializer/, api/)
- Created nginx/README.md placeholder documenting WU-07 routing plan

**Decisions**:
- Used named Docker network (planegraph-net) for inter-container communication
- Partition naming convention: position_reports_YYYYMMDD
- Config trigger fires on both INSERT and UPDATE for hot-reload support
- Runway extended centerlines: 15 NM (27780 m) via ST_Project over geography
- Airspace boundaries: geodetic ST_Buffer, not planar approximations

**Artifacts**:
- docker/docker-compose.yml
- docker/.env.example
- docker/postgres/postgresql.conf
- docker/postgres/init/00-extensions.sql
- docker/nginx/README.md
- migrations/001_core_schema.sql through 006_partition_management.sql
- migrations/run.sh
- services/ingest/, services/materializer/, services/api/ (stubs)

**Next**:
- [ ] Review and commit
- [ ] Deploy to edge02 and verify acceptance criteria
- [ ] Begin WU-02

---

### 2026-03-16 — Claude.ai Session 2 — GDR Review, Architecture Design, Implementation Spec

**Duration**: ~4h
**Scope**: Review GDR-02/03/04 outputs, design full application architecture, write 7-WU implementation spec

**Completed**:
- Reviewed GDR-02 output (segmentation pipeline architecture, postgresql.conf, schema DDL)
- Reviewed GDR-03 output (Columbus airspace geometry, runway coordinates, airspace boundaries, POIs)
- Reviewed GDR-04 output (web visualization survey — MapLibre + Deck.gl + PMTiles recommended)
- Designed full application architecture (ingest → materialization → API → frontend)
- Wrote consolidated IMPLEMENTATION.md specification
- Created 7 work unit specs (WU-01 through WU-07) with decision logs, deliverables, and acceptance criteria
- Validated cross-WU contracts (API → frontend, ingest → schema, config propagation)

**Decisions**:
- Frontend stack: React + MapLibre GL + Deck.gl + PMTiles (from GDR-04 survey)
- WebSocket for live aircraft feed (not polling)
- Configuration exposed in UI with trigger-based hot-reload to services
- 7 work units, sequential execution, ~10 nights estimated
- WU-01 is infrastructure-only (no Python services)
- dump978/UAT deferred past WU-07

**Artifacts**:
- spec/IMPLEMENTATION.md
- spec/wu-01-infrastructure/README.md through spec/wu-07-integration-polish/README.md
- spec/baseline-capture-report-2026-03-16.md

**Next**:
- [ ] Fire WU-01 to Claude Code on edge02
- [ ] Review WU-01 output

---

### 2026-03-15 — Claude.ai Session 1 — Project Bootstrap and Edge Node Setup

**Duration**: ~3h
**Scope**: GDR-01 prompt creation, edge02 hardware inventory, full node provisioning, baseline SDR testing, GDR-02/03 prompt creation

**Completed**:
- Wrote GDR-01 exploratory prompt (NSB methodology) and fired to Gemini Deep Research
- Inventoried edge02 hardware from `lshw` and shell history dumps
- Created edge02 infrastructure spec (`edge02-spec.md`) with hardware, network, software stack
- Wrote and executed full setup script on edge02:
  - Python venv at `/opt/planegraph/venv` with auto-activation via `/etc/profile.d/`
  - Node.js v24.14.0 + npm 11.9.0
  - OpenCode (authenticated with z.ai key)
  - Claude Code (native installer, authenticated)
  - rtl-sdr userspace tools, postgresql-client
  - Docker Compose 5.1.0, pre-pulled postgres:16-alpine and crystaldba/postgres-mcp
  - Blacklisted DVB kernel drivers, rebuilt initramfs
- Verified SDR dongles post-reboot: both NESDR SMArt v5 claimed by userspace, R820T tuners confirmed
- Ran baseline ADS-B test: `rtl_adsb -d 0` produced ~22 frames in 15 seconds from indoor window antenna, no LNA
- Received GDR-01 output from Gemini: 20 materializations, 4 embedding approaches, 6 graph patterns, viz priority matrix, data quality hazard register, 4 follow-on GDR recommendations
- Updated edge02-spec.md with SAWBird+ LNA specs (34dB gain, 0.8dB NF, dual SAW), CHENGPI IP65 outdoor enclosure, physical deployment diagram, signal chain
- Wrote GDR-02 (continuous segmentation pipeline) and GDR-03 (Columbus airspace geofence schema)

**Decisions**:
- Edge02 is the entire universe — all compute, storage, dev tooling, SDR hardware. No cluster dependency.
- Patio deployment: antennas bolted to fence (not tripod), enclosure at ground level, SAWBird+ inside enclosure
- Signal chain: Antenna 1 → SAWBird+ ADS-B channel → Dongle 0 (1090 MHz), Antenna 2 → SAWBird+ UAT channel → Dongle 1 (978 MHz), USB power from N100
- CrystalDB MCP in SSE mode on port 8000 for multi-client access (Claude Code + OpenCode simultaneously)
- Python venv at `/opt/planegraph/venv` is the default for all users and agent shells
- GDR-02 and GDR-03 can run in parallel — no dependencies between them
- GDR-04 (embeddings) and GDR-05 (Apache AGE) are blocked until GDR-02 output lands

**Artifacts**:
- `spec/gdr-01-planegraph-exploratory.md` — Phase 1 GDR prompt (pre-existing)
- `spec/gdr-02-continuous-segmentation-pipeline.md` — Phase 2 GDR prompt (new)
- `spec/gdr-03-columbus-airspace-geofence.md` — Phase 2 GDR prompt (new)
- `spec/README.md` — Updated with GDR status table
- `edge02-spec.md` — Infrastructure spec (in outputs, needs vault placement)
- `edge02-setup.sh` — Setup script (executed, can be archived)
- GDR-01 output received — needs to be saved as `spec/gdr-01-output-ads-b-data-science.md`

**Next**:
- [x] Fire GDR-02 and GDR-03 to Gemini (can run in parallel)
- [ ] Copy GDR-01 output into `spec/gdr-01-output-ads-b-data-science.md`
- [ ] Place `edge02-spec.md` into vault at `04-infrastructure/`
- [x] Review GDR-02/03 outputs when they land
- [x] Begin docker-compose stack (postgres + ultrafeeder) once GDR-02 output provides schema
- [x] Design doc / architecture document consolidating GDR outputs into implementation spec
