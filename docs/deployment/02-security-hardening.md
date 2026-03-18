<!--
---
title: "Security Hardening"
description: "CIS v8 IG1 security baseline application for the edge node"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Draft"
tags:
  - type: guide
  - domain: [deployment, security]
  - tech: docker
  - audience: intermediate
related_documents:
  - "[CIS v8 IG1 Baseline](../security/cis-v8-ig1-baseline.md)"
  - "[Ubuntu Base](01-ubuntu-base.md)"
---
-->

# Security Hardening

Applies the CIS Controls v8 Implementation Group 1 (IG1) security baseline to the Planegraph edge node. IG1 represents essential cyber hygiene — 56 safeguards focused on access control, secure configuration, audit logging, and vulnerability management.

This is a single-box deployment with no cluster dependencies, making it an unusually clean implementation of IG1 — every control either applies directly to this one machine or is explicitly N/A.

---

## 1. Purpose

Harden the Ubuntu 24.04 base installation against common threats. The edge node is internet-connected (WiFi), runs Docker containers with privileged access (ultrafeeder requires USB device access), and stores aviation data in PostgreSQL. The hardening must secure the system without breaking these operational requirements.

---

## 2. Prerequisites

- Ubuntu 24.04 LTS installed per [01-ubuntu-base.md](01-ubuntu-base.md)
- SSH access to the node
- Root or sudo access

---

## 3. Hardening Scope

### What We Harden

- SSH configuration (key-only auth, no root login, connection limits)
- Firewall (UFW — deny-default with explicit allows)
- Account policy (password complexity, sudo logging, dormant account lockout)
- Audit logging (auditd rules for privileged commands, file access, auth events)
- File integrity monitoring (AIDE baseline)
- Automatic security patching (unattended-upgrades)
- Malware scanning (rkhunter, chkrootkit on schedule)
- Time synchronization (chrony for accurate timestamps)
- Docker daemon hardening (logging, no insecure registries, userns-remap where possible)
- Kernel hardening (sysctl parameters for network stack)
- Service minimization (disable unused services)

### What We Cannot Harden Post-Install

- Full disk encryption (LUKS) — must be configured during OS installation
- LVM partition separation (/var, /tmp, /var/log on separate partitions) — must be done during install
- These are documented as accepted exceptions in the [compliance matrix](../security/cis-v8-ig1-baseline.md)

---

## 4. SSH Hardening

SSH is the primary remote access path. The goal is key-only authentication with no root login and aggressive session limits.

**Before making any changes, ensure your SSH public key is in `~/.ssh/authorized_keys`.** Disabling password authentication without a working key will lock you out.

### 4.1 Create the Hardening Drop-In

Add a drop-in file so the main `sshd_config` is left unchanged (Ubuntu uses `Include /etc/ssh/sshd_config.d/*.conf`):

```bash
sudo tee /etc/ssh/sshd_config.d/10-planegraph-hardening.conf > /dev/null << 'EOF'
# Planegraph SSH hardening — CIS v8 IG1

# Disable root login entirely
PermitRootLogin no

# Key-only authentication
PasswordAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no

# Brute-force mitigation
MaxAuthTries 3
MaxSessions 5

# Kill idle sessions after 10 minutes (300s × 2 checks)
ClientAliveInterval 300
ClientAliveCountMax 2

# Reduce attack surface
X11Forwarding no
AllowTcpForwarding no

# Login warning banner
Banner /etc/issue.net
EOF
```

### 4.2 Configure Login Banner

```bash
sudo tee /etc/issue.net > /dev/null << 'EOF'
*******************************************************************
* AUTHORIZED USERS ONLY                                           *
* This system is monitored. Unauthorized access is prohibited.    *
* Disconnect now if you are not authorized to use this system.    *
*******************************************************************
EOF
```

### 4.3 Apply and Verify

```bash
# Validate config syntax before restarting
sudo sshd -t

# Restart SSH daemon
sudo systemctl restart ssh

# Verify the service is healthy
sudo systemctl status ssh
```

**Test key-based login from another terminal before closing the current session:**

```bash
ssh crainbramp@edge02-ip hostname    # Must succeed
ssh -o PasswordAuthentication=yes crainbramp@edge02-ip    # Must fail: "Permission denied"
```

---

## 5. Firewall Configuration

UFW provides simple host-based firewall management. **Important**: Docker manages iptables rules directly and bypasses UFW for container-published ports. UFW rules only protect ports on the host's network interfaces, not Docker-forwarded ports.

### 5.1 Default Policy

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw default deny forward
```

### 5.2 Allow Required Services

```bash
# SSH — rate-limited (blocks IPs after 6 attempts in 30 seconds)
sudo ufw limit 22/tcp comment 'SSH (rate-limited)'

# tar1090 web UI — restrict to LAN (replace 192.168.1.0/24 with your subnet)
sudo ufw allow from 192.168.1.0/24 to any port 8080 proto tcp comment 'tar1090 web UI'

# SBS and Beast ports — localhost only (Docker containers on planegraph-net reach these internally)
sudo ufw allow from 127.0.0.1 to any port 30003 proto tcp comment 'SBS ingest (localhost)'
sudo ufw allow from 127.0.0.1 to any port 30005 proto tcp comment 'Beast protocol (localhost)'
```

PostgreSQL (5432) is not opened in UFW — the `planegraph-postgres` container is only reachable via the `planegraph-net` Docker bridge and from localhost. Docker adds its own iptables rules for published ports.

### 5.3 Enable UFW

```bash
sudo ufw enable
sudo ufw status verbose
```

### 5.4 Docker / UFW Interaction

Docker inserts `DOCKER-USER` chains into iptables before UFW's `ufw-before-forward` chain. This means Docker-published ports (e.g., `0.0.0.0:8080`) bypass UFW's INPUT rules and are accessible even if UFW would deny them. For the Planegraph deployment this is acceptable because:

- Port 8080 (tar1090) is only needed on LAN — not exposing to internet is handled at the router.
- Ports 30003 and 30005 are published on `127.0.0.1` only in `docker-compose.yml` (using `127.0.0.1:30003:30003`), so Docker's rules only accept connections from localhost.

If stricter LAN isolation is required, add rules to the `DOCKER-USER` iptables chain:

```bash
# Example: restrict 8080 to LAN from DOCKER-USER chain
sudo iptables -I DOCKER-USER -p tcp --dport 8080 ! -s 192.168.1.0/24 -j DROP
```

These iptables rules do not persist across reboots without additional tooling (e.g., `iptables-persistent`).

---

## 6. Account and Access Control

### 6.1 Verify Admin Accounts

Only `root` and `crainbramp` have login shells on edge02:

```bash
getent passwd | awk -F: '$7 ~ /(bash|sh|zsh)/ {print $1, $7}'
# Expected output:
# root /bin/bash
# crainbramp /bin/bash
```

No service accounts should have interactive shells. If any appear, change their shell to `/usr/sbin/nologin`.

### 6.2 Lock the Root Account

```bash
sudo passwd -l root
sudo passwd -S root    # Shows: root L ... (L = locked)
```

Root was locked on 2025-08-05 on edge02. The `crainbramp` account has passwordless sudo for operational convenience.

### 6.3 Configure Sudo Logging

```bash
sudo tee /etc/sudoers.d/planegraph-logging > /dev/null << 'EOF'
Defaults logfile="/var/log/sudo.log"
Defaults log_input, log_output
EOF

sudo chmod 440 /etc/sudoers.d/planegraph-logging

# Verify sudoers syntax
sudo visudo -c
```

### 6.4 Password Policy via PAM

```bash
sudo apt install -y libpam-pwquality

sudo tee /etc/security/pwquality.conf > /dev/null << 'EOF'
minlen = 12
minclass = 3
maxrepeat = 3
EOF
```

### 6.5 Password Aging

Edit `/etc/login.defs` to set maximum password age and warning period:

```bash
sudo sed -i 's/^PASS_MAX_DAYS.*/PASS_MAX_DAYS\t365/' /etc/login.defs
sudo sed -i 's/^PASS_WARN_AGE.*/PASS_WARN_AGE\t14/' /etc/login.defs
```

### 6.6 Verify No Empty Passwords

```bash
sudo awk -F: '($2 == "") {print "WARNING: empty password for " $1}' /etc/shadow
# Expected: no output
```

---

## 7. Audit Logging

Auditd provides kernel-level event logging for privileged operations. It is installed and enabled on edge02.

### 7.1 Install

```bash
sudo apt install -y auditd audispd-plugins
```

### 7.2 Planegraph Audit Rules

```bash
sudo tee /etc/audit/rules.d/planegraph.rules > /dev/null << 'EOF'
# Planegraph audit rules — CIS v8 IG1

## Delete all existing rules on load
-D

## Increase buffers to handle burst events (e.g., package installs)
-b 8192

## System identity file monitoring
-w /etc/passwd -p wa -k identity
-w /etc/shadow -p wa -k identity
-w /etc/group  -p wa -k identity
-w /etc/gshadow -p wa -k identity

## SSH config monitoring
-w /etc/ssh/sshd_config -p wa -k sshd_config
-w /etc/ssh/sshd_config.d/ -p wa -k sshd_config

## Sudo usage
-w /var/log/sudo.log -p wa -k sudo_log
-w /etc/sudoers -p wa -k sudoers
-w /etc/sudoers.d/ -p wa -k sudoers

## Privileged command execution (setuid/setgid binaries)
-a always,exit -F arch=b64 -S execve -C uid!=euid -F euid=0 -k setuid_exec
-a always,exit -F arch=b32 -S execve -C uid!=euid -F euid=0 -k setuid_exec

## Mount operations
-a always,exit -F arch=b64 -S mount -k mount_ops
-a always,exit -F arch=b32 -S mount -k mount_ops

## User and group management
-w /usr/sbin/useradd  -p x -k user_mgmt
-w /usr/sbin/usermod  -p x -k user_mgmt
-w /usr/sbin/userdel  -p x -k user_mgmt
-w /usr/sbin/groupadd -p x -k group_mgmt
-w /usr/sbin/groupmod -p x -k group_mgmt
-w /usr/sbin/groupdel -p x -k group_mgmt

## Login and logout events
-w /var/log/faillog -p wa -k auth_events
-w /var/log/lastlog -p wa -k auth_events
-w /var/run/faillock/ -p wa -k auth_events

## Make the configuration immutable (require reboot to change rules)
-e 2
EOF
```

### 7.3 Log Retention Configuration

Edit `/etc/audit/auditd.conf` to configure rotation:

```bash
sudo sed -i 's/^max_log_file =.*/max_log_file = 50/'         /etc/audit/auditd.conf
sudo sed -i 's/^max_log_file_action =.*/max_log_file_action = ROTATE/' /etc/audit/auditd.conf
sudo sed -i 's/^num_logs =.*/num_logs = 10/'                  /etc/audit/auditd.conf
```

### 7.4 Enable and Start

```bash
sudo systemctl enable auditd
sudo systemctl restart auditd

# Load the new rules
sudo augenrules --load

# Verify rules are loaded
sudo auditctl -l | head -20
```

### 7.5 Verify

```bash
# Check auditd is running
sudo systemctl status auditd

# Test: triggering an identity event
sudo touch /etc/passwd
sudo ausearch -k identity | tail -5
```

---

## 8. File Integrity Monitoring

AIDE (Advanced Intrusion Detection Environment) hashes all monitored files and alerts on unexpected changes.

### 8.1 Install

```bash
sudo apt install -y aide aide-common
```

### 8.2 Initialize the Baseline Database

This scan hashes every monitored file on the system. It takes 5–15 minutes on first run.

```bash
sudo aideinit
# Output: "AIDE, version x.x
#  ### AIDE database at /var/lib/aide/aide.db.new initialized."
```

Move the new database into the active position:

```bash
sudo cp /var/lib/aide/aide.db.new /var/lib/aide/aide.db
```

### 8.3 Schedule Daily Checks

```bash
# Add to root crontab — runs at 04:00 UTC daily
(sudo crontab -l 2>/dev/null; echo "0 4 * * * /usr/bin/aide --check 2>&1 | mail -s 'AIDE report: edge02' root") | sudo crontab -
```

If no mail server is configured, redirect output to a log file:

```bash
(sudo crontab -l 2>/dev/null; echo "0 4 * * * /usr/bin/aide --check >> /var/log/aide-check.log 2>&1") | sudo crontab -
```

### 8.4 Updating the Baseline After Intentional Changes

After applying system updates or known-good configuration changes, update the baseline:

```bash
sudo aide --update
sudo cp /var/lib/aide/aide.db.new /var/lib/aide/aide.db
```

Run this after every `apt upgrade` or intentional file deployment to prevent false positives on the next nightly check.

---

## 9. Automatic Security Updates

Unattended-upgrades is installed on edge02 and configured to apply Ubuntu security updates automatically.

### 9.1 Install and Enable

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

### 9.2 Configuration

The active configuration is at `/etc/apt/apt.conf.d/50unattended-upgrades`. The following settings are in effect:

```
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}";
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
    "${distro_id}ESM:${distro_codename}-infra-security";
};
```

To enable automatic reboots at a low-traffic window and email notifications, add the following to `/etc/apt/apt.conf.d/51planegraph-upgrades`:

```bash
sudo tee /etc/apt/apt.conf.d/51planegraph-upgrades > /dev/null << 'EOF'
// Automatically reboot if required after upgrades
Unattended-Upgrade::Automatic-Reboot "true";

// Reboot at 04:00 UTC (low-traffic window)
Unattended-Upgrade::Automatic-Reboot-Time "04:00";

// Remove unused kernel packages after upgrade
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-New-Unused-Dependencies "true";
EOF
```

### 9.3 Verify

```bash
sudo unattended-upgrade --dry-run --debug 2>&1 | head -30
```

Expected output includes `Packages that will be upgraded:` (may be empty if system is current).

---

## 10. Malware Scanning

Rkhunter and chkrootkit are installed on edge02. Both tools scan for known rootkits, suspicious files, and hidden processes.

### 10.1 Install

```bash
sudo apt install -y rkhunter chkrootkit
```

### 10.2 Initialize rkhunter Baseline

```bash
# Update the signature database
sudo rkhunter --update

# Record current system file properties as the known-good baseline
sudo rkhunter --propupd
```

### 10.3 Scheduled Scans

Rkhunter runs daily via `/etc/cron.daily/rkhunter` (installed by the package) and updates its database weekly via `/etc/cron.weekly/rkhunter`. These are active on edge02.

To add a chkrootkit weekly scan:

```bash
(sudo crontab -l 2>/dev/null; echo "0 3 * * 3 /usr/sbin/chkrootkit 2>&1 | grep -v 'not found' >> /var/log/chkrootkit.log") | sudo crontab -
```

### 10.4 Initial Scan and Expected Warnings

Run an initial scan and review the output:

```bash
sudo rkhunter --check --skip-keypress --report-warnings-only
sudo chkrootkit 2>&1 | grep -v 'not found'
```

**Expected false positives on a clean Ubuntu 24.04 system:**
- rkhunter may warn about `/usr/bin/lwp-request` or script interpreter paths — these are package-installed tools, not malware. After confirming, run `rkhunter --propupd` to update the baseline.
- chkrootkit may report `eth0: PROMISC` if Docker bridge interfaces are active — this is a known false positive from Docker's network configuration.

After package upgrades, always run `sudo rkhunter --propupd` to update the file property database and prevent false alarms on the next scheduled scan.

---

## 11. Kernel and Network Hardening

Ubuntu 24.04 ships with a number of sysctl hardening files under `/etc/sysctl.d/` (source address verification, kernel pointer restriction, etc.). The Planegraph overlay file adds remaining CIS controls and ensures Docker compatibility.

> **Note**: `net.ipv4.ip_forward = 1` is required for Docker's network routing. Disabling it breaks all container networking.

### 11.1 Create the Planegraph Sysctl Overlay

```bash
sudo tee /etc/sysctl.d/99-planegraph-hardening.conf > /dev/null << 'EOF'
# Planegraph kernel hardening — CIS v8 IG1
# Extends Ubuntu base sysctl files in /etc/sysctl.d/

# Required for Docker container networking
net.ipv4.ip_forward = 1

# Disable ICMP redirect sending (this host is not a router)
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# Ignore ICMP redirects (prevents route poisoning)
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv6.conf.default.accept_redirects = 0

# Log packets with impossible source addresses (martians)
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1

# Ignore broadcast pings (prevents Smurf amplification)
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Ignore bogus ICMP error responses
net.ipv4.icmp_ignore_bogus_error_responses = 1

# SYN cookie protection against SYN flood attacks
net.ipv4.tcp_syncookies = 1

# Full ASLR for all processes
kernel.randomize_va_space = 2

# Prevent setuid core dumps (leaks privilege escalation info)
fs.suid_dumpable = 0
EOF
```

### 11.2 Apply

```bash
sudo sysctl --system

# Verify key values
sysctl net.ipv4.tcp_syncookies net.ipv4.conf.all.log_martians kernel.randomize_va_space
```

Expected output:

```
net.ipv4.tcp_syncookies = 1
net.ipv4.conf.all.log_martians = 1
kernel.randomize_va_space = 2
```

> **Existing Ubuntu files**: `/etc/sysctl.d/10-network-security.conf` sets `rp_filter = 2` (strict) and `/etc/sysctl.d/10-kernel-hardening.conf` sets `kernel.kptr_restrict = 1`. The Planegraph overlay file does not duplicate these.

---

## 12. Docker Daemon Hardening

### 12.1 Create `/etc/docker/daemon.json`

```bash
sudo tee /etc/docker/daemon.json > /dev/null << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "no-new-privileges": true,
  "live-restore": true,
  "icc": false
}
EOF
```

**Settings rationale:**

| Setting | Value | Reason |
|---------|-------|--------|
| `log-driver` | `json-file` | Structured logs, avoids unbounded log growth |
| `log-opts.max-size` | `10m` | Cap per-container log file size |
| `log-opts.max-file` | `3` | Keep 3 rotated log files per container |
| `no-new-privileges` | `true` | Prevents container processes from gaining new capabilities via setuid |
| `live-restore` | `true` | Containers keep running if the Docker daemon restarts |
| `icc` | `false` | Disables unfiltered inter-container communication; containers can still communicate via named networks |

### 12.2 Apply and Verify

```bash
sudo systemctl reload docker || sudo systemctl restart docker

# Verify settings were applied
docker info | grep -E 'Logging Driver|ICC'
```

### 12.3 ultrafeeder Privileged Mode — Accepted Risk

The `planegraph-ultrafeeder` container runs with `privileged: true` because readsb requires direct access to the RTL-SDR USB devices. This is an accepted risk documented in the compliance matrix (CIS Control 4.6) with the following mitigations:

- The container image is from a trusted, actively maintained source ([sdr-enthusiasts/docker-adsb-ultrafeeder](https://github.com/sdr-enthusiasts/docker-adsb-ultrafeeder))
- The container's network access is restricted to `planegraph-net` — it does not have host networking
- The container does not mount any sensitive host paths other than `/dev/bus/usb`
- Automatic updates are enabled (`UPDATE_TAR1090=true`) to pull security patches

---

## 13. Time Synchronization

Accurate timestamps are critical for ADS-B data — `position_reports` records use `received_at` to correlate positions across time. Chrony is installed and enabled on edge02.

### 13.1 Install

```bash
sudo apt install -y chrony
```

### 13.2 Configuration

The default Ubuntu chrony configuration at `/etc/chrony/chrony.conf` is in use, targeting Ubuntu's NTP pools:

```
pool ntp.ubuntu.com        iburst maxsources 4
pool 0.ubuntu.pool.ntp.org iburst maxsources 1
pool 1.ubuntu.pool.ntp.org iburst maxsources 1
pool 2.ubuntu.pool.ntp.org iburst maxsources 2
```

These pools provide redundant stratum-2 sources with IPv4 and IPv6 coverage. No custom configuration is required.

### 13.3 Enable and Start

```bash
sudo systemctl enable chrony
sudo systemctl start chrony
```

### 13.4 Verify Synchronization

```bash
chronyc tracking
```

Expected output shows `System time` offset of a few milliseconds and `Leap status: Normal`. If the system is not yet synchronized, wait 30–60 seconds after first boot.

```bash
chronyc sources -v    # List NTP sources and their offset/reach
```

---

## 14. Service Minimization

### 14.1 Audit Enabled Services

```bash
systemctl list-unit-files --state=enabled
```

### 14.2 Enabled Services on edge02

The following services are enabled and their purpose documented:

| Service | Retained | Reason |
|---------|----------|--------|
| `apparmor.service` | Yes | Mandatory access control |
| `auditd.service` | Yes | Kernel audit logging |
| `chrony.service` | Yes | NTP time synchronization |
| `containerd.service` | Yes | Docker container runtime |
| `cron.service` | Yes | Scheduled tasks (backups, scans) |
| `docker.service` | Yes | Container engine |
| `fail2ban.service` | Yes | SSH brute-force protection |
| `netbird.service` | Yes | Zero-trust VPN for cluster connectivity |
| `networkd-dispatcher.service` | Yes | Network event handling |
| `postfix.service` | Yes | Local mail relay for cron job output |
| `prometheus-node-exporter.service` | Yes | Host metrics for monitoring |
| `rsyslog.service` | Yes | System log aggregation |
| `smartmontools.service` | Yes | SSD health monitoring |
| `snapd.service` | Yes | Ubuntu snap package manager (system dependency) |
| `sysstat.service` | Yes | Historical CPU/IO statistics |
| `thermald.service` | Yes | Intel thermal management for N100 |
| `ufw.service` | Yes | Firewall |
| `cloud-*.service` | No-op | Cloud-init services — active but no-op on bare metal |
| `liongard-agent.service` | Yes | Infrastructure monitoring agent |

### 14.3 Services Not Present (Already Absent)

The following services that are commonly disabled on hardened Ubuntu systems are not installed on edge02:

- `bluetooth.service` — not installed (no Bluetooth hardware in use)
- `cups.service` — not installed (no printing)
- `avahi-daemon.service` — not installed (no mDNS/zeroconf)

No services were manually disabled during hardening — the Ubuntu Server install does not include desktop or GUI services.

---

## 15. Fail2ban Configuration

Fail2ban monitors authentication logs and bans IPs that exceed retry thresholds. It is installed and enabled on edge02.

### 15.1 Install

```bash
sudo apt install -y fail2ban
```

### 15.2 Configure `jail.local`

Create `/etc/fail2ban/jail.local` (overrides defaults in `jail.conf`):

```bash
sudo tee /etc/fail2ban/jail.local > /dev/null << 'EOF'
[DEFAULT]
# Global defaults
bantime  = 3600      # Ban for 1 hour
findtime = 600       # Count failures within 10-minute windows
maxretry = 3         # Ban after 3 failures

[sshd]
enabled  = true
port     = ssh
logpath  = %(sshd_log)s
backend  = %(sshd_backend)s
maxretry = 3
bantime  = 3600
findtime = 600
EOF
```

### 15.3 Enable and Start

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### 15.4 Verify

```bash
# Check jail status
sudo fail2ban-client status
sudo fail2ban-client status sshd

# Check currently banned IPs
sudo fail2ban-client status sshd | grep 'Banned IP'
```

Expected output from `fail2ban-client status sshd`:
```
Status for the jail: sshd
|- Filter
|  |- Currently failed: 0
|  |- Total failed:     0
|  `- File list:        /var/log/auth.log
`- Actions
   |- Currently banned: 0
   |- Total banned:     0
   `- Banned IP list:
```

To manually unban an IP (e.g., if you locked yourself out during testing):

```bash
sudo fail2ban-client set sshd unbanip <ip-address>
```

---

## 16. Verification

After applying all hardening steps, run a Lynis audit to validate:

```bash
# Install if not present
apt install lynis

# Run full system audit
lynis audit system

# Review results — target hardening index of 80+
# Document the score and any remaining findings
```

The Lynis report provides a hardening index score and specific recommendations. A score of 80+ indicates a well-hardened system. Any findings that remain after this guide should be documented as accepted risks in the [compliance matrix](../security/cis-v8-ig1-baseline.md).

---

## 17. Next Step

Proceed to [SDR Configuration](03-sdr-configuration.md).

---

## 18. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
