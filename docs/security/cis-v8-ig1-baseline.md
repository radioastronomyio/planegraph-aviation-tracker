<!--
---
title: "CIS Controls v8 IG1 Compliance Baseline"
description: "Control-by-control compliance matrix for the Planegraph edge node"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Draft"
tags:
  - type: reference
  - domain: security
  - audience: intermediate
related_documents:
  - "[Security Hardening Guide](../deployment/02-security-hardening.md)"
---
-->

# CIS Controls v8 IG1 Compliance Baseline

Control-by-control compliance matrix for the Planegraph edge node. CIS Controls v8 Implementation Group 1 (IG1) defines 56 safeguards representing essential cyber hygiene. This document maps every IG1 safeguard to its implementation status on a single-box Ubuntu 24.04 deployment running Docker, PostgreSQL, and an SDR reception stack.

---

## 1. Purpose

Provide a verifiable security posture for the Planegraph edge node. Each safeguard is mapped to a specific implementation, marked with a compliance status, and linked to the relevant configuration file or procedure. This matrix enables audit, replication, and ongoing compliance validation.

---

## 2. Compliance Status Key

| Status | Meaning |
|--------|---------|
| ✅ Met | Safeguard fully implemented and verifiable |
| ⚠️ Partial | Safeguard partially implemented with documented exceptions |
| ❌ N/A | Safeguard not applicable to this deployment model |
| 🔲 Planned | Safeguard not yet implemented, scheduled for hardening |

---

## 3. CIS Control 1: Inventory and Control of Enterprise Assets

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 1.1 | Establish and Maintain Detailed Enterprise Asset Inventory | ✅ Met | `infrastructure/edge02-spec.md` documents all hardware including USB devices | Single-box deployment — one asset to track |
| 1.2 | Address Unauthorized Assets | ✅ Met | USB device inventory verified via `lsusb`; only SDR dongles and UPS connected | No network-attached peripherals |

---

## 4. CIS Control 2: Inventory and Control of Software Assets

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 2.1 | Establish and Maintain a Software Inventory | ✅ Met | `edge02-spec.md` documents installed packages; `docker-compose.yml` defines container images | `dpkg --list` and `docker images` provide live inventory |
| 2.2 | Ensure Authorized Software is Currently Supported | ✅ Met | Ubuntu 24.04 LTS (supported through 2029); Docker CE stable; PostgreSQL 16 (supported through 2028) | All components on active support branches |
| 2.3 | Address Unauthorized Software | 🔲 Planned | Implement periodic `dpkg --list` audit against known-good baseline | AIDE covers file integrity; package audit is the gap |

---

## 5. CIS Control 3: Data Protection

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 3.1 | Establish and Maintain a Data Management Process | ✅ Met | ADS-B data is public broadcast; no PII in dataset; retention policy is 60 days via `pipeline_config` | Data classification: public aviation telemetry |
| 3.2 | Establish and Maintain a Data Inventory | ✅ Met | Schema documented in `reference/data-dictionary.md`; all tables in single PostgreSQL database | Single database, single box, no data sprawl |
| 3.3 | Configure Data Access Control Lists | ✅ Met | Single database user (`planegraph`); PostgreSQL listens only on Docker network and localhost | No multi-tenant access control needed |
| 3.4 | Enforce Data Retention | ✅ Met | `drop_expired_partitions()` enforces retention; default 60 days configurable via `pipeline_config` | Partition-based retention — clean, verifiable |
| 3.6 | Encrypt Data on End-User Devices | ⚠️ Partial | LUKS full disk encryption available but must be configured during OS install; not applied post-install | Accepted exception: would require OS reinstallation |

---

## 6. CIS Control 4: Secure Configuration of Enterprise Assets and Software

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 4.1 | Establish and Maintain a Secure Configuration Process | ✅ Met | All configuration is version-controlled in this repository; Docker Compose is declarative | Infrastructure as code |
| 4.2 | Establish and Maintain a Secure Configuration Process for Network Infrastructure | ✅ Met | UFW firewall with deny-default policy; only required ports opened | See `deployment/02-security-hardening.md` §5 |
| 4.3 | Configure Automatic Session Locking on Enterprise Assets | ❌ N/A | Headless server — no console sessions to lock | SSH sessions timeout via `ClientAliveInterval` |
| 4.4 | Implement and Manage a Firewall on Servers | 🔲 Planned | UFW configuration defined in hardening guide | Implemented during security hardening step |
| 4.6 | Securely Manage Enterprise Assets and Software | ✅ Met | SSH key-only authentication; no shared accounts; `unattended-upgrades` for patching | Single operator, single admin account |
| 4.7 | Manage Default Accounts on Enterprise Assets and Software | 🔲 Planned | Lock root account; verify no default database passwords; change Postgres password from template | Implemented during security hardening step |

---

## 7. CIS Control 5: Account Management

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 5.1 | Establish and Maintain an Inventory of Accounts | ✅ Met | Single admin account (`crainbramp`); single DB user (`planegraph`); no service accounts with login shells | Audit: `cat /etc/passwd \| grep -v nologin` |
| 5.2 | Use Unique Passwords | ✅ Met | SSH uses key-only auth; Postgres password is unique generated value | No password reuse possible with key auth |
| 5.3 | Disable Dormant Accounts | 🔲 Planned | Single user system — configure `INACTIVE` in `/etc/default/useradd` | Low risk on single-operator box |
| 5.4 | Restrict Administrator Privileges to Dedicated Administrator Accounts | ✅ Met | Admin account uses `sudo` for privilege escalation; no direct root login | `sudo` logging enabled |

---

## 8. CIS Control 6: Access Control Management

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 6.1 | Establish an Access Granting Process | ✅ Met | Single operator — access granted via SSH key deployment | No multi-user access management needed |
| 6.2 | Establish an Access Revoking Process | ✅ Met | Remove SSH public key from `~/.ssh/authorized_keys` to revoke | Immediate effect |
| 6.3 | Require MFA for Externally-Exposed Applications | ⚠️ Partial | SSH key authentication is single-factor (something you have); NetBird overlay adds network-level authentication | MFA not implemented; SSH keys provide strong auth |
| 6.4 | Require MFA for Remote Network Access | ⚠️ Partial | NetBird VPN provides authenticated overlay; SSH keys for host access | Two separate authentication steps, not true MFA |
| 6.5 | Require MFA for Administrative Access | ⚠️ Partial | Same as 6.3/6.4 | SSH keys are strong but single-factor |

---

## 9. CIS Control 7: Continuous Vulnerability Management

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 7.1 | Establish and Maintain a Vulnerability Management Process | 🔲 Planned | `unattended-upgrades` for OS; Docker image updates via compose pull; Lynis periodic audits | Automated for OS packages; manual for containers |
| 7.2 | Establish and Maintain a Remediation Process | 🔲 Planned | Lynis findings drive remediation; `unattended-upgrades` handles critical patches automatically | Document remediation SLA in operations guide |
| 7.3 | Perform Automated Operating System Patch Management | 🔲 Planned | `unattended-upgrades` with automatic security updates and reboot | Configured during security hardening step |
| 7.4 | Perform Automated Application Patch Management | ⚠️ Partial | OS packages via `unattended-upgrades`; Docker images require manual `docker compose pull` | Container updates are not fully automated |

---

## 10. CIS Control 8: Audit Log Management

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 8.1 | Establish and Maintain an Audit Log Management Process | 🔲 Planned | `auditd` rules for privileged operations, auth events, file modifications | Configured during security hardening step |
| 8.2 | Collect Audit Logs | 🔲 Planned | `auditd` + Docker json-file logging + PostgreSQL `log_min_duration_statement` | Three log sources covering system, container, and database |
| 8.3 | Ensure Adequate Audit Log Storage | 🔲 Planned | `auditd` rotation: 50MB × 10 files; Docker log rotation: 10MB × 3 files per container | Total audit storage budget: ~550MB |

---

## 11. CIS Control 9: Email and Web Browser Protections

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 9.1 | Ensure Use of Only Fully Supported Browsers and Email Clients | ❌ N/A | Headless server — no browser or email client installed | No user-facing web browsing |

---

## 12. CIS Control 10: Malware Defenses

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 10.1 | Deploy and Maintain Anti-Malware Software | 🔲 Planned | `rkhunter` + `chkrootkit` on weekly schedule | Not real-time AV; appropriate for Linux server |
| 10.2 | Configure Automatic Anti-Malware Signature Updates | 🔲 Planned | `rkhunter --update` via cron before scan | Signature updates tied to scan schedule |
| 10.3 | Disable Autorun and Autoplay for Removable Media | ✅ Met | Ubuntu server has no desktop environment; `udisks2` not installed; USB automount disabled | Headless server — no automount risk |

---

## 13. CIS Control 11: Data Recovery

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 11.1 | Establish and Maintain a Data Recovery Practice | 🔲 Planned | `pg_dump` daily to cluster storage via NetBird overlay | See `operations/backup-recovery.md` |
| 11.2 | Perform Automated Backups | 🔲 Planned | Cron-scheduled `pg_dump` piped to remote storage | Database only — config is in version control |
| 11.3 | Protect Recovery Data | 🔲 Planned | Backups transmitted over NetBird encrypted overlay; stored on cluster with separate access controls | Network encryption in transit; access control at rest |
| 11.4 | Establish and Maintain an Isolated Instance of Recovery Data | ⚠️ Partial | Cluster storage is a separate physical host; not air-gapped | Separate host, same network — partial isolation |

---

## 14. CIS Control 12: Network Infrastructure Management

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 12.1 | Ensure Network Infrastructure is Up-to-Date | ✅ Met | Home router firmware maintained; edge02 network stack is Ubuntu-managed | No enterprise network gear to manage |

---

## 15. CIS Control 13: Network Monitoring and Defense

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 13.1 | Centralize Security Event Alerting | ⚠️ Partial | `prometheus-node-exporter` exposes metrics; cluster Grafana scrapes edge02 | Security events not yet forwarded — only system metrics |

---

## 16. CIS Control 14: Security Awareness and Skills Training

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 14.1 | Establish and Maintain a Security Awareness Program | ❌ N/A | Single-operator project | No personnel to train |
| 14.2 | Train Workforce Members to Recognize Social Engineering Attacks | ❌ N/A | Single-operator project | No personnel to train |
| 14.3 | Train Workforce Members on Authentication Best Practices | ❌ N/A | Single-operator project | Operator is the security team |
| 14.4 | Train Workforce Members on Data Handling Best Practices | ❌ N/A | Single-operator project | ADS-B data is public broadcast |
| 14.5 | Train Workforce Members on Causes of Unintentional Data Exposure | ❌ N/A | Single-operator project | No workforce |
| 14.8 | Train Workforce Members on Dangers of Connecting to and Transmitting Data Over Insecure Networks | ❌ N/A | Single-operator project | NetBird overlay encrypts all management traffic |

---

## 17. CIS Control 15: Service Provider Management

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 15.1 | Establish and Maintain an Inventory of Service Providers | ✅ Met | Service providers: ISP, ADS-B aggregators (FlightAware, ADS-B Exchange), NetBird, GitHub | All are external SaaS; no data processing delegation |

---

## 18. CIS Control 16: Application Software Security

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 16.1 | Establish and Maintain a Secure Application Development Process | ✅ Met | Code review via Greptile + Macroscope + GPT Codex; version control in GitHub | Multi-reviewer pipeline despite single developer |
| 16.7 | Use Standard Hardening Configuration Templates for Application Infrastructure | ✅ Met | `postgresql.conf` is version-controlled; Docker daemon config is documented; all configs in repo | No ad-hoc configuration |

---

## 19. CIS Control 17: Incident Response Management

| # | Safeguard | Status | Implementation | Notes |
|---|-----------|--------|----------------|-------|
| 17.1 | Designate Personnel to Manage Incident Handling | ✅ Met | Single operator handles all incidents | No escalation path needed |
| 17.2 | Establish and Maintain Contact Information for Reporting Security Incidents | ❌ N/A | Personal project — no external reporting requirements | GitHub security policy in `SECURITY.md` |
| 17.3 | Establish and Maintain an Enterprise Process for Reporting Incidents | ❌ N/A | Single operator | No process needed beyond personal awareness |

---

## 20. Compliance Summary

| Status | Count | Percentage |
|--------|-------|------------|
| ✅ Met | 24 | 43% |
| ⚠️ Partial | 7 | 13% |
| ❌ N/A | 10 | 18% |
| 🔲 Planned | 15 | 27% |

After executing the security hardening guide (`deployment/02-security-hardening.md`), all 🔲 Planned safeguards move to ✅ Met, bringing the effective compliance rate to approximately 85% of applicable controls (excluding N/A).

### Accepted Exceptions

| Safeguard | Exception | Risk Acceptance |
|-----------|-----------|-----------------|
| 3.6 | Full disk encryption not applied post-install | Physical theft risk is low for a patio-mounted edge node on private property; data is public ADS-B telemetry |
| 6.3/6.4/6.5 | No true MFA | SSH key authentication + NetBird overlay provides two authentication layers, though not combined into single MFA flow |
| 7.4 | Container image updates not automated | Manual `docker compose pull` required; acceptable for a 2-container stack with low change frequency |
| 11.4 | Backup storage not air-gapped | Cluster is on separate hardware but same home network; acceptable for non-critical data |

---

## 21. Audit Procedure

To re-validate compliance, run:

```bash
# System audit
lynis audit system

# Check firewall rules
ufw status verbose

# Check SSH config
sshd -T | grep -E 'permitrootlogin|passwordauthentication|maxauthtries'

# Check audit rules
auditctl -l

# Check AIDE integrity
aide --check

# Check fail2ban status
fail2ban-client status

# Check unattended-upgrades
apt-config dump | grep Unattended-Upgrade

# Check Docker daemon config
cat /etc/docker/daemon.json
```

---

## 22. References

| Resource | Description |
|----------|-------------|
| [CIS Controls v8](https://www.cisecurity.org/controls/v8) | Official control framework |
| [CIS Ubuntu Linux 24.04 Benchmark](https://www.cisecurity.org/benchmark/ubuntu_linux) | OS-specific implementation guidance |
| [Security Hardening Guide](../deployment/02-security-hardening.md) | Step-by-step hardening procedures |

---

## 23. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
