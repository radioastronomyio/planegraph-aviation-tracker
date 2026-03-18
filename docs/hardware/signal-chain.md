<!--
---
title: "Signal Chain"
description: "RF signal path from antenna through LNA to SDR dongle and USB"
author: "VintageDon (https://github.com/vintagedon)"
date: "2026-03-17"
version: "1.0"
status: "Active"
tags:
  - type: reference
  - domain: reception
  - tech: rtl-sdr
  - audience: all
related_documents:
  - "[Bill of Materials](bill-of-materials.md)"
  - "[SDR Configuration](../deployment/03-sdr-configuration.md)"
---
-->

# Signal Chain

The RF signal path from antenna to application. Understanding this chain is essential for diagnosing reception issues and optimizing performance.

---

## 1. Overview

The Planegraph receiver captures ADS-B transmissions from aircraft on 1090 MHz (and optionally 978 MHz UAT) using a dedicated receive chain per frequency. Each chain follows the same pattern: antenna → coaxial cable → LNA with SAW filtering → SDR dongle → USB to host computer.

```
Antenna (5dBi)
    │
    │ 10ft N-to-SMA coax (~1.5 dB loss)
    │
SAWbird+ LNA
    │ SAW filter → LNA stage → SAW filter
    │ +34 dB gain, 0.8 dB noise figure
    │
NESDR SMArt v5 (RTL2832U + R820T2)
    │ Tuner → ADC → USB
    │
N100 USB port
    │
readsb decoder (Docker)
    │
SBS output → port 30003
```

---

## 2. Dual-Channel Configuration

The SAWbird+ ADS-B is a dual-channel device with independent signal paths for each frequency:

```
Antenna 1 (1090 MHz) ──► SAWbird+ ADS-B Input ──► SAWbird+ ADS-B Output ──► Dongle 0 (device 0)
Antenna 2 (978 MHz)  ──► SAWbird+ UAT Input   ──► SAWbird+ UAT Output   ──► Dongle 1 (device 1)
                                │
                          USB power from N100 (5V, 300mA)
```

All connections are SMA. The SAWbird+ is powered via USB from the N100 — only one power source should be connected (USB, bias-tee, or pin header, never multiple).

---

## 3. SAWbird+ LNA Specifications

| Parameter | ADS-B Channel (1090 MHz) | UAT Channel (978 MHz) |
|-----------|--------------------------|----------------------|
| Gain | +34 dB | +35 dB |
| 3dB Bandwidth | 8 MHz | 15 MHz |
| Noise Figure | 0.8 dB | 0.8 dB |
| Noise Temperature | 59 K | 59 K |
| Out-of-band Rejection | +85 dB | +85 dB |
| Output P1dB | 19 dBm | 19 dBm |
| Input Return Loss | -14 to -10 dB | -11 to -10 dB |

Each channel has two cascaded SAW filters (4 total in the device) providing sharp bandpass filtering. This is critical for outdoor deployment — without SAW filtering, strong nearby transmitters (cell towers, FM broadcast) can overload the SDR front-end and cause intermodulation products that mask ADS-B signals.

---

## 4. Link Budget

Approximate receive-side link budget for a typical commercial aircraft at 100 NM range:

| Stage | Value | Notes |
|-------|-------|-------|
| Aircraft EIRP | +54 dBm | Typical 1090 MHz transponder output |
| Free space path loss (100 NM) | -137 dB | At 1090 MHz, 185 km |
| Antenna gain | +5 dBi | Fiberglass omnidirectional |
| Cable loss | -1.5 dB | 10ft RG-316 at 1090 MHz |
| LNA gain | +34 dB | SAWbird+ ADS-B channel |
| LNA noise figure | 0.8 dB | Dominates system noise figure |
| Signal at SDR input | **-45.5 dBm** | Well above RTL-SDR sensitivity (~-85 dBm) |

This provides approximately 40 dB of margin, which accounts for antenna orientation losses, atmospheric effects, multipath, and the fact that aircraft are not always at optimal aspect angle. At shorter ranges (Columbus area traffic is typically 20–60 NM), the margin increases substantially.

---

## 5. Physical Deployment

### Antenna Placement

The antennas are mounted to a fence line approximately 15 feet from the house, cresting the top of the fence for maximum sky visibility. Height above ground is approximately 6 feet. This is not optimal (a rooftop mount at 20+ feet would be significantly better) but provides adequate coverage of the Columbus Class C airspace out to approximately 100–150 NM in most directions.

### Enclosure Layout

```
┌─────────────────────────────────────┐
│          IP65 Steel Enclosure       │
│                                     │
│  ┌───────────────┐  ┌───────────┐  │
│  │  SAWbird+ LNA │  │   UPS     │  │
│  │  (USB powered)│  │  (74Wh)   │  │
│  └──┬────────┬──┘  │  12V→N100 │  │
│     │SMA  SMA│     │  5V→LNA   │  │
│  ┌──┴──┐ ┌──┴──┐  └───────────┘  │
│  │ SDR │ │ SDR │                   │
│  │  0  │ │  1  │  ┌───────────┐   │
│  └──┬──┘ └──┬──┘  │   N100    │   │
│     └───USB──┴─────│  Mini PC  │   │
│                    └───────────┘   │
│        [WiFi to home AP]           │
└─────────────────────────────────────┘
     │              │
  Antenna 1      Antenna 2
  (1090 MHz)     (978 MHz)
```

Cable runs from antenna to enclosure are approximately 10 feet. Inside the enclosure, SMA connections from SAWbird+ to dongles are less than 1 foot. Minimizing cable length after the antenna and before the LNA preserves signal quality.

---

## 6. Gain Tuning

The ultrafeeder container manages SDR gain automatically when configured with `READSB_GAIN=autogain`. This is the recommended setting for initial deployment. The autogain algorithm adjusts gain to maximize message rate while avoiding ADC saturation.

For manual tuning, the R820T2 tuner in the NESDR SMArt v5 supports 29 gain steps from 0.0 to 49.6 dB. With the SAWbird+ providing +34 dB of pre-amplification, the SDR tuner gain should typically be set lower (10–25 dB) than it would be without an LNA. Setting tuner gain too high with an LNA in the chain will cause ADC saturation and actually reduce message decode rates.

Signs of over-amplification: message rate drops as gain increases, strong signal message percentage is very high (>50%), and the noise floor is elevated. Reduce SDR gain until message rate peaks.

---

## 7. References

| Resource | Description |
|----------|-------------|
| [Bill of Materials](bill-of-materials.md) | Component purchase list |
| [SDR Configuration](../deployment/03-sdr-configuration.md) | Software setup for this hardware |
| [Nooelec SAWbird+ ADS-B](https://www.nooelec.com/store/sawbird-plus-adsb.html) | LNA product page and datasheet |
| [RTL-SDR Blog Gain Guide](https://www.rtl-sdr.com/tag/gain/) | Community gain tuning reference |

---

## 8. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
