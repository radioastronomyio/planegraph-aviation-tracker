<!--
---
title: "Deployment"
description: "Step-by-step deployment guides from OS installation to running application stack"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: deployment
  - tech: [docker, postgres, readsb]
---
-->

# Deployment

Step-by-step guides for deploying the Planegraph platform from bare metal to running system. Follow the numbered sequence in order — each guide assumes the previous step is complete.

---

## 1. Contents

```
deployment/
├── 01-ubuntu-base.md           # OS installation and initial configuration
├── 02-security-hardening.md    # CIS v8 IG1 baseline hardening
├── 03-sdr-configuration.md     # SDR driver setup and verification
├── 04-application-stack.md     # Docker Compose, database, migrations
├── 05-verification.md          # End-to-end acceptance testing
└── README.md                   # This file
```

---

## 2. Deployment Sequence

| Step | Guide | Duration | Prerequisites |
|------|-------|----------|---------------|
| 1 | [Ubuntu Base](01-ubuntu-base.md) | ~30 min | Hardware assembled per [BOM](../hardware/bill-of-materials.md) |
| 2 | [Security Hardening](02-security-hardening.md) | ~20 min | Ubuntu installed and accessible via SSH |
| 3 | [SDR Configuration](03-sdr-configuration.md) | ~15 min | OS configured, SDR dongles connected via USB |
| 4 | [Application Stack](04-application-stack.md) | ~15 min | OS hardened, Docker installed, SDR verified |
| 5 | [Verification](05-verification.md) | ~10 min | Application stack running |

Total deployment time from bare metal: approximately 90 minutes for an experienced operator, 2–3 hours for a first-time build.

---

## 3. Related

| Document | Relationship |
|----------|--------------|
| [docs/](../README.md) | Parent directory |
| [Hardware BOM](../hardware/bill-of-materials.md) | Component list for this deployment |
| [Security Baseline](../security/cis-v8-ig1-baseline.md) | CIS compliance matrix |
| [Operations](../operations/README.md) | Post-deployment management |
