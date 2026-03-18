<!--
---
title: "Infrastructure"
description: "Edge node hardware specifications and deployment environment documentation"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: deployment
  - tech: [ubuntu, docker, rtl-sdr]
---
-->

# Infrastructure

Hardware specifications and deployment environment for the Planegraph edge node. This is a single-box deployment — edge02 is the entire compute environment with no cluster dependencies.

---

## 1. Contents

```
infrastructure/
├── edge02-spec.md      # Full hardware inventory, network config, software stack
└── README.md           # This file
```

---

## 2. Documents

| Document | Description |
|----------|-------------|
| [edge02-spec.md](edge02-spec.md) | Complete edge node specification — CPU, RAM, storage, SDR dongles, LNA specs, network topology (wired office → WiFi patio), installed software, and development tooling |

---

## 3. Deployment Phases

The edge node operates in two physical configurations:

| Phase | Location | Network | Antenna | Status |
|-------|----------|---------|---------|--------|
| Office (current) | Upstairs office, antenna out window | Wired (enp3s0, 10.16.207.127) | Indoor, no LNA | ✅ Active |
| Patio (target) | Outdoor enclosure on patio fence | WiFi (wlp2s0) via home AP | Outdoor mount, SAWbird+ LNA | 📋 Planned |

NetBird overlay VPN maintains reachability regardless of physical location or local IP changes.

---

## 4. Related

| Document | Relationship |
|----------|--------------|
| [Repository Root](../README.md) | Parent directory |
| [Hardware BOM](../docs/hardware/bill-of-materials.md) | Component purchase list |
| [Signal Chain](../docs/hardware/signal-chain.md) | RF signal path design |
| [Deployment Guides](../docs/deployment/README.md) | OS install through verification |
