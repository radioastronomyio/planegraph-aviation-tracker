<!--
---
title: "Hardware"
description: "Bill of materials, signal chain, and physical assembly documentation"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: reception
  - tech: rtl-sdr
---
-->

# Hardware

Bill of materials, signal chain design, and physical assembly documentation for the Planegraph edge node. Everything needed to replicate the hardware platform.

---

## 1. Contents

```
hardware/
├── bill-of-materials.md    # Complete parts list with costs and alternatives
├── signal-chain.md         # RF path from antenna to USB, with specs
└── README.md               # This file
```

---

## 2. Documents

| Document | Description |
|----------|-------------|
| [bill-of-materials.md](bill-of-materials.md) | Full parts list with purchase links, costs, and substitution notes |
| [signal-chain.md](signal-chain.md) | RF signal path, LNA specifications, cable routing, physical deployment |

---

## 3. Related

| Document | Relationship |
|----------|--------------|
| [docs/](../README.md) | Parent directory |
| [SDR Configuration](../deployment/03-sdr-configuration.md) | Software setup for SDR hardware |
