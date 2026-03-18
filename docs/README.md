<!--
---
title: "Documentation"
description: "Project documentation including hardware, deployment, security, operations, and reference materials"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "2.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: documentation
---
-->

# Documentation

Complete documentation for building, deploying, hardening, and operating the Planegraph ADS-B platform. Designed for reproducibility — anyone with the same hardware should be able to go from bare metal to running system using these docs.

---

## 1. Contents

```
docs/
├── hardware/                       # Parts list, signal chain, physical build
├── deployment/                     # Step-by-step from OS install to running stack
├── security/                       # CIS v8 IG1 baseline and compliance matrix
├── reference/                      # Data dictionary, config keys, Docker services
├── operations/                     # Day-to-day management, backup, troubleshooting
├── documentation-standards/        # Template library and tagging strategy
└── README.md                       # This file
```

---

## 2. Reading Order

For a new build, follow the documentation in this order:

| Step | Document | What You'll Do |
|------|----------|----------------|
| 1 | [Hardware BOM](hardware/bill-of-materials.md) | Purchase components |
| 2 | [Signal Chain](hardware/signal-chain.md) | Understand RF path and assemble |
| 3 | [Ubuntu Base](deployment/01-ubuntu-base.md) | Install and configure OS |
| 4 | [Security Hardening](deployment/02-security-hardening.md) | Apply CIS v8 IG1 baseline |
| 5 | [SDR Configuration](deployment/03-sdr-configuration.md) | Blacklist drivers, verify dongles |
| 6 | [Application Stack](deployment/04-application-stack.md) | Docker Compose, migrations, services |
| 7 | [Verification](deployment/05-verification.md) | End-to-end acceptance tests |

For ongoing operations, see [Operations](operations/README.md). For schema details, see [Reference](reference/README.md).

---

## 3. Subdirectories

| Directory | Description |
|-----------|-------------|
| [hardware/](hardware/README.md) | Bill of materials, signal chain, physical assembly |
| [deployment/](deployment/README.md) | Numbered deployment guides from OS install through verification |
| [security/](security/README.md) | CIS v8 IG1 compliance baseline and hardening documentation |
| [reference/](reference/README.md) | Data dictionary, configuration keys, Docker service reference |
| [operations/](operations/README.md) | Service management, backup/recovery, troubleshooting |
| [documentation-standards/](documentation-standards/README.md) | Templates for READMEs, KB articles, script headers, tagging |

---

## 4. Related

| Document | Relationship |
|----------|--------------|
| [Repository Root](../README.md) | Parent directory |
| [AGENTS.md](../AGENTS.md) | Agent instructions and project context |
