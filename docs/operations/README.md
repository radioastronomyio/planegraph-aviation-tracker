<!--
---
title: "Operations"
description: "Day-to-day management, backup, recovery, and troubleshooting"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: deployment
---
-->

# Operations

Day-to-day management documentation for the running Planegraph platform. Covers backup and recovery procedures, service management, monitoring, and troubleshooting common issues.

---

## 1. Contents

```
operations/
├── backup-recovery.md      # pg_dump schedule, restore procedure, verification
├── troubleshooting.md      # Common issues and diagnostic procedures
└── README.md               # This file
```

---

## 2. Documents

| Document | Description |
|----------|-------------|
| [backup-recovery.md](backup-recovery.md) | Database backup schedule, restore procedure, and backup verification |
| [troubleshooting.md](troubleshooting.md) | Diagnostic procedures for common issues (no signal, database full, service crashes) |

---

## 3. Quick Reference

### Service Management

```bash
# Start/stop/restart the stack
docker compose -f docker/docker-compose.yml up -d
docker compose -f docker/docker-compose.yml down
docker compose -f docker/docker-compose.yml restart

# View logs (follow mode)
docker compose -f docker/docker-compose.yml logs -f

# Check container health
docker compose -f docker/docker-compose.yml ps
```

### Health Checks

```bash
# Postgres accepting connections
docker compose -f docker/docker-compose.yml exec planegraph-postgres pg_isready -U planegraph

# Aircraft being received
curl -sf http://localhost:8080/data/aircraft.json | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'{len(d.get(\"aircraft\", []))} aircraft')"

# Disk usage
df -h /var/lib/docker
```

---

## 4. Related

| Document | Relationship |
|----------|--------------|
| [docs/](../README.md) | Parent directory |
| [Docker Services](../reference/docker-services.md) | Service definitions and common commands |
| [Deployment](../deployment/README.md) | Initial setup procedures |
