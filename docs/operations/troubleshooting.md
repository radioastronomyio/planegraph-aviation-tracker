<!--
---
title: "Troubleshooting"
description: "Diagnostic procedures for common issues"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Draft"
tags:
  - type: guide
  - domain: [deployment, reception]
  - tech: [docker, postgres, readsb, rtl-sdr]
  - audience: intermediate
related_documents:
  - "[Docker Services](../reference/docker-services.md)"
  - "[Signal Chain](../hardware/signal-chain.md)"
---
-->

# Troubleshooting

Diagnostic procedures for common operational issues. Organized by symptom — find what's broken, follow the diagnostic steps.

---

## 1. No Aircraft Visible

### Symptoms

- tar1090 map at `:8080` shows no aircraft
- `curl localhost:8080/data/aircraft.json` returns `{"aircraft": []}`
- SBS port 30003 produces no output

### Diagnostic Steps

1. **Container running?**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml ps
   ```
   `planegraph-ultrafeeder` must show `running (healthy)`. If it shows `exited` or `restarting`, go to §6.

2. **Check ultrafeeder logs for SDR errors:**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       logs planegraph-ultrafeeder | tail -50
   ```
   Look for `No supported devices found` (dongle not seen) or `Failed to open rtlsdr device` (driver conflict).

3. **Is the dongle visible on USB?**
   ```bash
   lsusb | grep -i rtl
   ```
   Expected: `Realtek Semiconductor Corp. RTL2838 DVB-T`. If absent, the dongle is physically disconnected or powered off.

4. **Has a kernel driver reclaimed the dongle?**
   ```bash
   lsmod | grep dvb
   ```
   If any `dvb_*` modules appear, the blacklist failed to apply (e.g., after a kernel update). Reload it:
   ```bash
   sudo modprobe -r dvb_usb_rtl28xxu rtl2832 rtl2830 dvb_core dvb_usb_v2
   ```
   The blacklist at `/etc/modprobe.d/blacklist-rtlsdr.conf` should prevent this on next boot.

5. **Test the dongle directly** (stop ultrafeeder first):
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       stop planegraph-ultrafeeder
   rtl_test -d 0 -t
   ```
   A working dongle prints `Found 1 device(s)` and shows a sample rate test. Press Ctrl-C to stop, then restart ultrafeeder.

6. **Check antenna and LNA:**
   - Confirm the SMA cable is firmly seated at the LNA input and the SDR dongle.
   - Confirm the LNA's USB power cable is plugged in (the SAWbird+ requires 5V via USB — the LNA LED should be lit).
   - Aircraft count will drop to near-zero if the LNA loses power, even if the SDR is receiving.

7. **Gain too high or too low?** Check current gain in readsb stats:
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       exec planegraph-ultrafeeder \
       cat /run/readsb/stats.json | jq '.last1min.local.strong_signals // "n/a"'
   ```
   `strong_signals` > 50% indicates ADC saturation — lower the gain. See [Signal Chain §6](../hardware/signal-chain.md).

---

## 2. Database Connection Refused

### Symptoms

- `psql` returns "connection refused"
- Migration runner fails at connection stage
- API services (WU-03+) report database unavailable

### Diagnostic Steps

1. **Container running?**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml ps
   ```
   `planegraph-postgres` must show `running (healthy)`. If it shows `exited`, check step 2.

2. **Check postgres logs:**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       logs planegraph-postgres | tail -50
   ```
   Common error strings: `no space left on device` (go to §3), `invalid configuration parameter` (config syntax error), `password authentication failed`.

3. **Is the container healthy?**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       exec planegraph-postgres pg_isready -U planegraph
   ```
   Expected: `/var/run/postgresql:5432 - accepting connections`. If not, the database is still starting or has crashed.

4. **Is port 5432 bound?**
   ```bash
   ss -tlnp | grep 5432
   ```
   Expected: `LISTEN ... 0.0.0.0:5432`. If absent, the container is not running or host networking is misconfigured.

5. **Check credentials in `.env`:**
   ```bash
   grep POSTGRES_PASSWORD /opt/planegraph/repo/docker/.env
   ```
   Confirm the password matches what clients use. A mismatch between `.env` and the initialized volume will cause auth failures.

6. **Check disk space:**
   ```bash
   df -h /
   docker system df
   ```
   PostgreSQL will refuse to start (or crash mid-operation) if the volume is full. If disk is the cause, see §3 before restarting the container.

---

## 3. Disk Space Running Low

### Symptoms

- `df -h` shows >80% usage on root or Docker volume
- PostgreSQL starts refusing writes
- Docker container health checks fail

### Diagnostic Steps

1. **Overall disk usage:**
   ```bash
   df -h /
   ```
   >80% warrants action. >95% is an emergency — PostgreSQL may already be refusing writes.

2. **Docker layer and volume usage:**
   ```bash
   docker system df
   ```
   Shows images, containers, volumes, and build cache. The `postgres_data` volume dominates.

3. **Find the largest database partitions:**
   ```sql
   -- Run from psql -h localhost -U planegraph -d planegraph
   SELECT inhrelid::regclass AS partition,
          pg_size_pretty(pg_total_relation_size(inhrelid::regclass)) AS size
   FROM   pg_inherits
   WHERE  inhparent = 'position_reports'::regclass
   ORDER  BY pg_total_relation_size(inhrelid::regclass) DESC
   LIMIT  10;
   ```

4. **Check retention configuration:**
   ```sql
   SELECT * FROM pipeline_config WHERE key = 'retention_days';
   ```
   If retention is set to 60 days and disk is full, reduce it (e.g., to 30) and run cleanup.

5. **Run manual partition cleanup:**
   ```sql
   SELECT drop_expired_partitions();
   ```
   This drops partitions older than `retention_days`. Disk space is reclaimed immediately.

6. **Prune Docker images and stopped containers:**
   ```bash
   docker system prune -f
   ```
   Reclaims space from dangling images and stopped containers. Does **not** remove volumes.

**Preventive action:** Set a monitoring alert at 75% disk usage. On a 256 GB SSD with 60-day retention, expect ~40–80 GB for the database depending on traffic volume.

---

## 4. High CPU or Memory Usage

### Symptoms

- System becomes sluggish
- `htop` shows sustained high CPU or memory pressure
- Container OOM kills in Docker logs

### Diagnostic Steps

1. **Identify the top consumer:**
   ```bash
   htop
   ```
   Press `F6` → sort by `CPU%` or `MEM%`. Note the process name and PID.

2. **Check Docker container resource usage:**
   ```bash
   docker stats --no-stream
   ```
   Shows CPU %, memory, and network I/O per container. Identifies if ultrafeeder, postgres, or an application service is responsible.

3. **Check for long-running PostgreSQL queries:**
   ```sql
   -- Run from psql -h localhost -U planegraph -d planegraph
   SELECT pid,
          now() - query_start AS duration,
          state,
          LEFT(query, 80) AS query_snippet
   FROM   pg_stat_activity
   WHERE  state = 'active'
     AND  now() - query_start > interval '30 seconds'
   ORDER  BY duration DESC;
   ```
   Kill a stuck query: `SELECT pg_terminate_backend(<pid>);`

4. **Check for autovacuum on large partitions:**
   ```sql
   SELECT query FROM pg_stat_activity WHERE query LIKE 'autovacuum%';
   ```
   Autovacuum on a large `position_reports` partition is normal and self-limiting. It will finish. Do not kill autovacuum workers.

5. **Check partition maintenance activity:**
   ```sql
   SELECT * FROM pg_stat_activity WHERE query LIKE '%drop_expired%' OR query LIKE '%create_partition%';
   ```
   Partition creation/expiration runs briefly and completes in seconds. Sustained high CPU from partition operations indicates a loop or error.

**Common root causes:** autovacuum on large partitions (wait it out), an unindexed query hitting a full partition scan (check `pg_stat_statements`), or a connection leak from the ingest daemon (check connection count: `SELECT COUNT(*) FROM pg_stat_activity;`).

---

## 5. SDR Gain Issues

### Symptoms

- Aircraft count is lower than expected
- tar1090 shows "strong signals" percentage >50%
- Range is significantly reduced despite good antenna placement

### Diagnostic Steps

1. **Check current reception statistics:**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       exec planegraph-ultrafeeder \
       cat /run/readsb/stats.json | jq '.last1min | {messages, local}'
   ```
   Key fields: `local.accepted` (decoded messages), `local.strong_signals` (% of messages at ADC ceiling).

2. **Is autogain active?**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       exec planegraph-ultrafeeder \
       cat /run/readsb/autogain.log 2>/dev/null | tail -20
   ```
   If autogain is running, it adjusts every few minutes. Allow 30 minutes after container start for it to converge before intervening.

3. **Interpret `strong_signals` percentage:**
   - `strong_signals` > 50%: SDR gain too high, ADC is saturating. The SAWbird+ LNA provides +34 dB — the SDR tuner only needs 10–25 dB additional gain.
   - `strong_signals` < 5% and message count is low: gain may be too low, or antenna/LNA issue.

4. **Manually set gain for testing** (override `.env` temporarily):
   ```bash
   # Stop container, update .env, restart
   # Set READSB_GAIN=20 (or another value in 0–49.6 range) in docker/.env
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       up -d planegraph-ultrafeeder
   ```
   Monitor message rate vs. gain over 5-minute windows. Set `READSB_GAIN=autogain` to return to automatic control.

See [Signal Chain §6](../hardware/signal-chain.md) for full gain tuning reference.

---

## 6. Container Won't Start After Update

### Symptoms

- `docker compose up -d` fails after `docker compose pull`
- Container exits immediately with error in logs

### Diagnostic Steps

1. **Read the exit logs:**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       logs <service> | tail -50
   ```
   The last few lines before exit usually name the problem. Common patterns: `exec format error` (wrong architecture image), `permission denied`, config parsing errors.

2. **Check what image version was pulled:**
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml images
   ```
   Compare the `TAG` and `IMAGE ID` against the previous known-good run.

3. **PostgreSQL major version upgrade:**
   If the postgres image was updated from one major version to another (e.g., 15 → 16), the data directory format is incompatible. **Do not attempt to start the new version against the old volume.** Instead:
   ```bash
   # Export with old version before upgrade
   pg_dump -h localhost -U planegraph -d planegraph -Fc -f /tmp/pre-upgrade.dump
   # Then: down -v, new version up, pg_restore
   ```
   Always back up before pulling postgres image updates.

4. **Ultrafeeder environment variable changes:**
   New ultrafeeder versions occasionally deprecate or rename environment variables. Check the upstream changelog:
   ```bash
   docker compose -f /opt/planegraph/repo/docker/docker-compose.yml \
       exec planegraph-ultrafeeder cat /CONTAINER_VERSION 2>/dev/null
   ```
   Compare against release notes at the [sdr-enthusiasts/docker-adsb-ultrafeeder](https://github.com/sdr-enthusiasts/docker-adsb-ultrafeeder) repository.

5. **Roll back to the previous image digest:**
   ```bash
   # Find the previous digest in docker inspect or pull history
   docker inspect planegraph-ultrafeeder | jq '.[].Image'
   # Pull a specific digest
   docker pull ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder@sha256:<previous-digest>
   # Update compose to pin the digest, then restart
   ```

**Prevention:** Pin image tags or digests in `docker-compose.yml` for production. Test `docker compose pull` on a maintenance window, not during peak observation hours.

---

## 7. References

| Resource | Description |
|----------|-------------|
| [Docker Services](../reference/docker-services.md) | Container management reference |
| [Signal Chain](../hardware/signal-chain.md) | RF diagnostics and gain tuning |
| [Verification](../deployment/05-verification.md) | Full acceptance test suite |

---

## 8. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
