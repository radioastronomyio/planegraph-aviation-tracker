<!--
---
title: "Security"
description: "CIS v8 IG1 security baseline and compliance documentation"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: security
---
-->

# Security

CIS Controls v8 Implementation Group 1 (IG1) security baseline for the Planegraph edge node. IG1 represents essential cyber hygiene — the minimum set of controls every organization should implement.

This is a single-box deployment with a single operator, which makes full IG1 compliance achievable with minimal overhead. The compliance matrix documents every IG1 safeguard and its implementation status on this system.

---

## 1. Contents

```
security/
├── cis-v8-ig1-baseline.md     # Control-by-control compliance matrix
└── README.md                   # This file
```

---

## 2. Documents

| Document | Description |
|----------|-------------|
| [cis-v8-ig1-baseline.md](cis-v8-ig1-baseline.md) | Full IG1 compliance matrix with implementation status per safeguard |

---

## 3. Related

| Document | Relationship |
|----------|--------------|
| [docs/](../README.md) | Parent directory |
| [Security Hardening Guide](../deployment/02-security-hardening.md) | Step-by-step hardening procedures |
