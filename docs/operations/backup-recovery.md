<!--
---
title: "Backup and Recovery"
description: "Database backup schedule, restore procedures, and backup verification"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Draft"
tags:
  - type: guide
  - domain: deployment
  - tech: postgres
  - audience: intermediate
related_documents:
  - "[Docker Services](../reference/docker-services.md)"
  - "[CIS v8 IG1 Baseline](../security/cis-v8-ig1-baseline.md)"
---
-->

# Backup and Recovery

Database backup schedule, restore procedures, and backup verification for the Planegraph platform. Covers daily automated backups to cluster storage and manual recovery scenarios.

---

## 1. Purpose

Protect against data loss from hardware failure, corruption, or operator error. ADS-B data is non-recoverable once lost — the aircraft have moved on. The backup strategy must balance storage constraints (256GB SSD) against retention requirements (60 days of position reports).

---

## 2. Backup Strategy

### What Gets Backed Up

- PostgreSQL database (`planegraph`) — contains all position reports, flight sessions, reference geometry, and configuration
- Docker `.env` file — contains receiver coordinates and database credentials (not in version control)

### What Does NOT Need Backup

- Docker container images — pulled from public registries
- Schema and migrations — version-controlled in this repository
- Application code — version-controlled in this repository
- ultrafeeder state — ephemeral, reconstructed on container start

---

## 3. Automated Backup

The backup script lives at `/opt/planegraph/scripts/backup.sh`. A cron entry runs it daily at 2:00 AM UTC. If the scripts directory does not yet exist, create it: `sudo mkdir -p /opt/planegraph/scripts`.

**Script: `/opt/planegraph/scripts/backup.sh`**

```bash
#!/bin/bash
# Planegraph daily database backup
# Destination: local staging, then cluster via NetBird
# Retention:   7 daily backups locally, 30 on cluster

set -euo pipefail

BACKUP_DIR="/opt/planegraph/backups"
LOG_FILE="/var/log/planegraph-backup.log"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
FILENAME="planegraph-${TIMESTAMP}.dump"
DUMP_PATH="${BACKUP_DIR}/${FILENAME}"
MIN_SIZE_BYTES=10240          # fail if dump < 10 KB
KEEP_LOCAL=7                  # daily backups to retain on this host

mkdir -p "${BACKUP_DIR}"

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "${LOG_FILE}"; }

log "INFO  backup start: ${FILENAME}"

# Dump in custom format — compressed, supports selective restore
if pg_dump -h localhost -U planegraph -d planegraph -Fc -f "${DUMP_PATH}"; then
    ACTUAL_SIZE=$(stat -c%s "${DUMP_PATH}")
    if [ "${ACTUAL_SIZE}" -lt "${MIN_SIZE_BYTES}" ]; then
        log "ERROR dump too small (${ACTUAL_SIZE} bytes) — possible empty database"
        exit 1
    fi
    log "INFO  dump complete: ${DUMP_PATH} ($(numfmt --to=iec "${ACTUAL_SIZE}"))"
else
    log "ERROR pg_dump failed with exit code $?"
    exit 1
fi

# Rotate local backups — keep N most recent
find "${BACKUP_DIR}" -name 'planegraph-*.dump' -type f \
    | sort | head -n -"${KEEP_LOCAL}" | xargs -r rm --
log "INFO  local rotation complete (keeping ${KEEP_LOCAL})"

# Ship to cluster storage via NetBird (uncomment when cluster target is configured)
# CLUSTER_DIR="/mnt/cluster/planegraph-backups"
# rsync -az "${DUMP_PATH}" "${CLUSTER_DIR}/"
# find "${CLUSTER_DIR}" -name 'planegraph-*.dump' | sort | head -n -30 | xargs -r rm --
# log "INFO  cluster sync complete"

log "INFO  backup finished OK"
```

**Deploy and schedule:**

```bash
sudo mkdir -p /opt/planegraph/scripts
sudo cp backup.sh /opt/planegraph/scripts/backup.sh
sudo chmod +x /opt/planegraph/scripts/backup.sh

# Add to root crontab — runs at 02:00 UTC daily
(sudo crontab -l 2>/dev/null; echo "0 2 * * * /opt/planegraph/scripts/backup.sh") | sudo crontab -

# Verify
sudo crontab -l | grep backup
```

**Test before relying on cron:**

```bash
sudo /opt/planegraph/scripts/backup.sh
tail -20 /var/log/planegraph-backup.log
ls -lh /opt/planegraph/backups/
```

---

## 4. Manual Backup

For ad-hoc backups before risky operations (schema changes, major version upgrades):

```bash
pg_dump -h localhost -U planegraph -d planegraph -Fc -f /tmp/planegraph-$(date +%Y%m%d-%H%M%S).dump
```

---

## 5. Restore Procedure

### Scenario 1: Same-Host Restore (corruption recovery)

```bash
# 1. Stop all services that touch the database
cd /opt/planegraph/repo/docker
docker compose down

# 2. Destroy the database volume (all data is lost — restore from backup)
docker compose down -v

# 3. Start a fresh PostgreSQL container
docker compose up -d planegraph-postgres

# 4. Wait for the container to become healthy
docker compose ps          # wait until status shows "(healthy)"

# 5. Restore from backup
pg_restore -h localhost -U planegraph -d planegraph \
    --clean --if-exists \
    /opt/planegraph/backups/planegraph-YYYYMMDD-HHMMSS.dump

# 6. Restart remaining services
docker compose up -d

# 7. Verify (see docs/deployment/05-verification.md)
psql -h localhost -U planegraph -d planegraph -c "SELECT COUNT(*) FROM position_reports;"
```

### Scenario 2: New-Host Restore (hardware replacement)

```bash
# 1. Complete fresh deployment per guides 01-ubuntu-base through 04-application-stack
#    (OS install, Docker, Python venv, application stack)

# 2. Copy the latest backup from cluster storage (or secure transfer)
rsync -az user@cluster:/path/to/planegraph-latest.dump /opt/planegraph/backups/

# 3. Restore database (same as Scenario 1, steps 3–6)

# 4. Update receiver coordinates in docker/.env with the new host's GPS position
#    READSB_LAT, READSB_LON, READSB_ALT must match the physical antenna location.
```

### Scenario 3: Selective Table Restore

```bash
# Restore a single table without touching others
pg_restore -h localhost -U planegraph -d planegraph \
    --table=position_reports \
    /opt/planegraph/backups/planegraph-YYYYMMDD-HHMMSS.dump

# List available tables in a dump file (without restoring)
pg_restore --list /opt/planegraph/backups/planegraph-YYYYMMDD-HHMMSS.dump | grep TABLE
```

---

## 6. Backup Verification

**Script: `/opt/planegraph/scripts/verify-backup.sh`**

```bash
#!/bin/bash
# Weekly backup verification — restores latest dump to a temp database and
# runs sanity checks. Logs results; exits non-zero on failure.

set -euo pipefail

LOG_FILE="/var/log/planegraph-backup.log"
BACKUP_DIR="/opt/planegraph/backups"
TEST_DB="planegraph_verify_$$"
MAX_AGE_HOURS=25        # alert if newest backup is older than this

log() { echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ') $*" | tee -a "${LOG_FILE}"; }

# Find latest backup
LATEST=$(find "${BACKUP_DIR}" -name 'planegraph-*.dump' -type f | sort | tail -1)
if [ -z "${LATEST}" ]; then
    log "ERROR verify: no backup files found in ${BACKUP_DIR}"
    exit 1
fi

# Check age
AGE_HOURS=$(( ($(date +%s) - $(stat -c %Y "${LATEST}")) / 3600 ))
if [ "${AGE_HOURS}" -gt "${MAX_AGE_HOURS}" ]; then
    log "WARN  verify: newest backup is ${AGE_HOURS}h old (threshold: ${MAX_AGE_HOURS}h)"
fi

log "INFO  verify: testing ${LATEST} (age: ${AGE_HOURS}h)"

# Create temp database and restore
psql -h localhost -U planegraph -d postgres -c "CREATE DATABASE ${TEST_DB};"
trap "psql -h localhost -U planegraph -d postgres -c 'DROP DATABASE IF EXISTS ${TEST_DB};'" EXIT

pg_restore -h localhost -U planegraph -d "${TEST_DB}" "${LATEST}"

# Check tables exist
TABLES=$(psql -h localhost -U planegraph -d "${TEST_DB}" -tAc \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';")
log "INFO  verify: ${TABLES} tables restored"

# Row count sanity checks
POS_COUNT=$(psql -h localhost -U planegraph -d "${TEST_DB}" -tAc \
    "SELECT COUNT(*) FROM position_reports;" 2>/dev/null || echo 0)
log "INFO  verify: position_reports has ${POS_COUNT} rows"

# PostGIS sanity
POSTGIS_OK=$(psql -h localhost -U planegraph -d "${TEST_DB}" -tAc \
    "SELECT PostGIS_Version();" 2>/dev/null | tr -d ' ')
log "INFO  verify: PostGIS version ${POSTGIS_OK}"

if [ "${TABLES}" -lt 3 ]; then
    log "ERROR verify: too few tables — backup may be incomplete"
    exit 1
fi

log "INFO  verify: PASSED"
```

**Schedule weekly verification:**

```bash
sudo chmod +x /opt/planegraph/scripts/verify-backup.sh

# Run every Sunday at 03:00 UTC
(sudo crontab -l 2>/dev/null; echo "0 3 * * 0 /opt/planegraph/scripts/verify-backup.sh") | sudo crontab -
```

---

## 7. Disaster Recovery Scenarios

| Scenario | RTO | RPO | Procedure |
|----------|-----|-----|-----------|
| Container crash | Minutes | 0 | Docker auto-restart handles this |
| Database corruption | ~30 min | Last backup (≤24h) | Restore from latest dump |
| SSD failure | ~3 hours | Last backup (≤24h) | Replace SSD, reinstall, restore |
| Complete box loss | ~4 hours | Last backup (≤24h) | New hardware, full deployment + restore |

RTO = Recovery Time Objective (how long until service is restored).
RPO = Recovery Point Objective (how much data can be lost).

---

## 8. References

| Resource | Description |
|----------|-------------|
| [Docker Services](../reference/docker-services.md) | Container management commands |
| [Verification Guide](../deployment/05-verification.md) | Post-restore validation tests |
| [CIS Control 11](../security/cis-v8-ig1-baseline.md) | Data recovery compliance requirements |

---

## 9. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
