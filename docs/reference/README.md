<!--
---
title: "Reference"
description: "Data dictionary, configuration keys, and Docker service reference"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: directory-readme
  - domain: [schema, deployment]
---
-->

# Reference

Lookup documentation for the Planegraph database schema, configuration system, and Docker services. These are the docs you reach for when you need to know what a column means, what a config key does, or how a container is wired.

---

## 1. Contents

```
reference/
├── data-dictionary.md      # All tables, columns, types, and aviation domain context
├── configuration-keys.md   # pipeline_config keys, defaults, and propagation behavior
├── docker-services.md      # Container definitions, ports, volumes, health checks
└── README.md               # This file
```

---

## 2. Documents

| Document | Description |
|----------|-------------|
| [data-dictionary.md](data-dictionary.md) | Column-level reference for all database tables with aviation domain context |
| [configuration-keys.md](configuration-keys.md) | Pipeline configuration keys, default values, and hot-reload behavior |
| [docker-services.md](docker-services.md) | Container definitions, exposed ports, volume mounts, and health checks |

---

## 3. Related

| Document | Relationship |
|----------|--------------|
| [docs/](../README.md) | Parent directory |
| [Migrations](../../migrations/README.md) | SQL source for schema documented here |
| [Docker](../../docker/README.md) | Compose source for services documented here |
