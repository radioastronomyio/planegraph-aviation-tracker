<!--
---
title: "SDR Configuration"
description: "RTL-SDR driver setup, dongle verification, and baseline reception testing"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: guide
  - domain: [deployment, reception]
  - tech: rtl-sdr
  - audience: intermediate
related_documents:
  - "[Signal Chain](../hardware/signal-chain.md)"
  - "[Application Stack](04-application-stack.md)"
---
-->

# SDR Configuration

Driver setup and hardware verification for the RTL-SDR dongles. This step ensures the Linux kernel yields the USB devices to userspace tools rather than claiming them as DVB-T television receivers.

---

## 1. Purpose

By default, Linux loads kernel DVB drivers for RTL2832U-based devices, which prevents userspace tools (readsb, rtl_test, rtl_adsb) from accessing the dongles. This guide blacklists those kernel drivers, installs userspace RTL-SDR tools, and verifies reception.

---

## 2. Prerequisites

- Ubuntu 24.04 LTS configured per [01-ubuntu-base.md](01-ubuntu-base.md) and [02-security-hardening.md](02-security-hardening.md)
- SDR dongles connected via USB
- Root or sudo access

---

## 3. Blacklist Kernel DVB Drivers

Create a blacklist file to prevent the kernel from loading DVB drivers for the RTL2832U chipset:

```bash
cat > /etc/modprobe.d/blacklist-rtlsdr.conf << 'EOF'
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2830
blacklist dvb_usb_rtl2832u
blacklist dvb_core
blacklist dvb_usb_v2
EOF
```

Rebuild the initial ramdisk and reboot:

```bash
update-initramfs -u
reboot
```

---

## 4. Install Userspace RTL-SDR Tools

```bash
apt install rtl-sdr
```

This provides `rtl_test`, `rtl_adsb`, `rtl_fm`, `rtl_power`, and the `librtlsdr` library.

---

## 5. Verify Dongle Detection

After reboot, verify both dongles are detected by userspace:

```bash
# Check USB device tree — dongles should show with no kernel driver attached
lsusb -t | grep -i rtl

# Test dongle 0
rtl_test -d 0 -t
# Expected: "No E4000 tuner found, using default generic R820T tuner"
# Should report "R820T tuner" and exit cleanly with Ctrl+C

# Test dongle 1
rtl_test -d 1 -t
# Same expected output
```

If `rtl_test` reports "usb_open error -3" or "Permission denied", check that the user is in the `plugdev` group and that no kernel DVB modules are loaded (`lsmod | grep dvb` should return nothing).

---

## 6. Baseline Reception Test

With at least one antenna connected, test raw ADS-B reception:

```bash
# Receive ADS-B frames for 15 seconds on dongle 0
timeout 15 rtl_adsb -d 0

# Expected: decoded ADS-B frames printed to stdout
# *8da12345581234567890ab;
# Each line starting with * is a decoded Mode S message
```

In a typical metropolitan area with outdoor antennas, you should see multiple frames per second. Indoor reception with no LNA will produce fewer frames (1–3 per second) — this is normal and confirms the hardware chain is functional. Full performance requires the SAWbird+ LNA and outdoor antenna placement.

---

## 7. Dongle Identification

If running two dongles, identify them by serial number for consistent device assignment:

```bash
rtl_eeprom -d 0
rtl_eeprom -d 1
```

The ultrafeeder container uses device index (0, 1) by default. If dongles swap USB ports on reboot, you can assign persistent serial numbers with `rtl_eeprom -s NEW_SERIAL` — but for a single-box build with fixed USB wiring, this is usually unnecessary.

---

## 8. Gain Verification

The R820T2 tuner supports 29 gain steps. Verify the gain table is accessible:

```bash
rtl_test -d 0 -t 2>&1 | grep "Supported gain"
# Expected: "Supported gain values (29): 0.0 0.9 1.4 2.7 3.7 ... 49.6"
```

Gain tuning is handled automatically by the ultrafeeder container (`READSB_GAIN=autogain`). Manual gain adjustment is documented in the [Signal Chain](../hardware/signal-chain.md) reference.

---

## 9. Verification Checklist

| Check | Command | Expected |
|-------|---------|----------|
| No DVB modules loaded | `lsmod \| grep dvb` | No output |
| Dongle 0 accessible | `rtl_test -d 0 -t` | Reports R820T tuner |
| Dongle 1 accessible | `rtl_test -d 1 -t` | Reports R820T tuner |
| ADS-B frames received | `timeout 15 rtl_adsb -d 0` | At least 1 frame |
| Gain table readable | `rtl_test -d 0 -t 2>&1 \| grep "Supported gain"` | 29 gain values |

---

## 10. Next Step

Proceed to [Application Stack](04-application-stack.md).

---

## 11. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
