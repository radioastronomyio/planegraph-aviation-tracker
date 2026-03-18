<!--
---
title: "Ubuntu Base Installation"
description: "OS installation and initial system configuration for the edge node"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Draft"
tags:
  - type: guide
  - domain: deployment
  - tech: docker
  - audience: intermediate
related_documents:
  - "[Security Hardening](02-security-hardening.md)"
  - "[Hardware BOM](../hardware/bill-of-materials.md)"
---
-->

# Ubuntu Base Installation

OS installation and initial system configuration for the Planegraph edge node. This guide covers Ubuntu 24.04 LTS server installation, base package setup, user configuration, and Docker installation.

---

## 1. Purpose

Establish a clean Ubuntu 24.04 LTS base with Docker, development tooling, and network connectivity. This step produces a system that is accessible via SSH and ready for security hardening.

---

## 2. Prerequisites

- Hardware assembled per the [Bill of Materials](../hardware/bill-of-materials.md)
- Ubuntu 24.04 LTS Server ISO on USB boot media
- Keyboard and monitor for initial installation (can be removed after SSH is configured)
- Network connectivity (wired preferred for installation, WiFi configured later if needed)

---

## 3. OS Installation

### 3.1 Boot

1. Write the Ubuntu 24.04 LTS Server ISO to USB (e.g., `dd` or Balena Etcher).
2. Boot the N100 from USB. On the ACEMAGICIAN N100, press **F7** at POST for the boot menu.
3. Select **Try or Install Ubuntu Server**.

### 3.2 Installation Options

4. Language: **English**.
5. Keyboard: **English (US)**.
6. Base install type: **Ubuntu Server** (not minimized — the minimized variant omits some tools needed later).
7. Network: accept the default DHCP configuration. A static IP or DHCP reservation can be set after installation.
8. Mirror: accept the default Ubuntu archive.
9. Storage: select **Custom storage layout**:
   - 512 MB EFI partition (`/boot/efi`, FAT32)
   - 2 GB partition for `/boot` (ext4)
   - Remaining disk → **LVM volume group** → one logical volume for `/`

   > **LUKS full-disk encryption**: If encryption is required, check **Encrypt the LVM group with LUKS** at this step. This cannot be added post-install and is documented as an accepted exception if skipped. On edge02, LUKS was not configured.

### 3.3 Identity and SSH

10. Your name: (operator name)
11. Server name (hostname): `edge02`
12. Username: `crainbramp`
13. Password: (strong password; will be disabled later in favor of SSH keys)
14. Enable **Install OpenSSH server** — check this box.
15. Skip **Import SSH identity** (keys are added manually after first boot).

### 3.4 Snaps

16. Skip all optional snap installs. No snaps are needed for this deployment.

### 3.5 First Boot

17. Wait for installation to complete, then remove the USB and reboot.
18. Log in as `crainbramp`. SSH access should be available immediately from the local network.

```bash
# Verify from another machine
ssh crainbramp@<edge02-ip> hostname    # Returns: edge02
```

---

## 4. Post-Install Base Configuration

### 4.1 Update System Packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt autoremove -y
```

### 4.2 Set Timezone

UTC is used on edge02 for consistent ADS-B timestamps across all database records.

```bash
sudo timedatectl set-timezone UTC
timedatectl    # Verify: "Time zone: UTC (UTC, +0000)"
```

### 4.3 Install Base Packages

```bash
sudo apt install -y \
    build-essential \
    git \
    neovim \
    tree \
    tmux \
    curl \
    jq \
    socat \
    locate \
    htop \
    python3 \
    python3-venv \
    python3-pip

sudo updatedb    # Populate the locate database
```

### 4.4 Network Connectivity

This deployment uses a DHCP reservation on the home router — the N100's MAC address is assigned a fixed IP. No Netplan changes are required.

```bash
# Confirm connectivity
curl -s https://httpbin.org/ip | jq .origin

# Confirm hostname resolves locally
hostname -I
```

---

## 5. Docker Installation

Docker CE is installed from Docker's official repository. The Ubuntu-packaged `docker.io` is not used — it lags significantly behind upstream releases.

### 5.1 Add Docker Repository

```bash
sudo apt install -y ca-certificates curl

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
```

### 5.2 Install Docker CE

```bash
sudo apt install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
```

Installed on edge02: **Docker 29.3.0**, **Docker Compose v5.1.0**.

### 5.3 Post-Install Configuration

```bash
# Add admin user to the docker group (no sudo needed for docker commands)
sudo usermod -aG docker crainbramp

# Enable Docker to start at boot
sudo systemctl enable docker

# Apply group change in the current session
newgrp docker
```

### 5.4 Verify

```bash
docker run --rm hello-world    # Should print "Hello from Docker!"
docker compose version         # Should show v2.x or v5.x
```

---

## 6. Python Virtual Environment

The project uses a shared Python virtual environment at `/opt/planegraph/venv` with automatic activation for all interactive shells.

### 6.1 Create the Virtual Environment

```bash
sudo mkdir -p /opt/planegraph
sudo python3 -m venv /opt/planegraph/venv
sudo chown -R crainbramp:crainbramp /opt/planegraph/venv
```

### 6.2 Auto-Activation for All Shells

Create `/etc/profile.d/planegraph-venv.sh` so any interactive login shell activates the venv automatically:

```bash
sudo tee /etc/profile.d/planegraph-venv.sh > /dev/null << 'EOF'
#!/bin/bash
# Auto-activate PlanGraph venv for all interactive shells
if [ -d "/opt/planegraph/venv" ] && [ -z "$VIRTUAL_ENV" ]; then
    source /opt/planegraph/venv/bin/activate
fi
EOF
sudo chmod +x /etc/profile.d/planegraph-venv.sh
```

Open a new shell and verify:

```bash
which python    # /opt/planegraph/venv/bin/python
python --version    # Python 3.12.x
```

### 6.3 Upgrade pip

```bash
pip install --upgrade pip
```

Application-specific packages (`asyncpg`, `fastapi`, `uvicorn`, etc.) are installed during their respective work unit deployments, not here.

---

## 7. Development Tooling (Optional)

These tools are needed for AI-assisted development on the box but are not required for a production-only deployment.

### 7.1 Node.js

Required for Claude Code. Install from the NodeSource repository:

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs
node --version    # v24.x on edge02
```

### 7.2 Claude Code

Claude Code is installed via npm and runs from `~/.local/bin/claude`:

```bash
npm install -g @anthropic-ai/claude-code
```

After first run, confirm it is on `PATH`:

```bash
which claude    # /home/crainbramp/.local/bin/claude
claude --version
```

### 7.3 PostgreSQL Client

Provides `psql`, `pg_dump`, and `pg_restore` on the host for running migrations and ad-hoc queries without entering the Docker container:

```bash
sudo apt install -y postgresql-client
psql --version    # psql (PostgreSQL) 16.x
```

### 7.4 RTL-SDR Userspace Tools

Provides `rtl_test`, `rtl_sdr`, `rtl_power`, and `rtl_fm` for direct dongle testing:

```bash
sudo apt install -y rtl-sdr
rtl_test --help
```

The kernel driver blacklist for RTL-SDR is configured in [SDR Configuration](03-sdr-configuration.md) and lives at `/etc/modprobe.d/blacklist-rtlsdr.conf`.

---

## 8. Verification

At the end of this step, verify:

```bash
# OS is current
lsb_release -a                    # Ubuntu 24.04 LTS
uname -r                          # 6.8.x kernel

# Docker is operational
docker run --rm hello-world       # Prints success message
docker compose version            # 2.x+

# Python venv is active
which python                      # /opt/planegraph/venv/bin/python
python --version                  # 3.12+

# SSH is accessible from another machine
ssh user@edge02-ip hostname       # Returns hostname
```

---

## 9. Next Step

Proceed to [Security Hardening](02-security-hardening.md).

---

## 10. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
