<!--
---
title: "Bill of Materials"
description: "Complete parts list for the Planegraph ADS-B edge node"
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
  - "[Signal Chain](signal-chain.md)"
  - "[SDR Configuration](../deployment/03-sdr-configuration.md)"
---
-->

# Bill of Materials

Complete parts list for building a Planegraph edge node. All components are consumer-grade and available from Amazon or Nooelec direct. Total cost for the full outdoor deployment is approximately $350–$450 USD depending on sourcing.

---

## 1. Core Compute

| Component | Model | Key Specs | Notes |
|-----------|-------|-----------|-------|
| Edge Computer | ACEMAGICIAN N100 Mini PC | Intel N100 (4C/4T, 3.4GHz boost), 12GB LPDDR5, 256GB SATA SSD, dual GbE, WiFi 5 | 6W TDP / 15W turbo. Fanless options exist but this model has internal fan. RAM is soldered, not expandable. |

The N100 is the sweet spot for this project — enough compute for PostgreSQL, Docker, and Python services, low enough power draw (15W turbo) to run on a small UPS indefinitely. Any x86 mini PC with 8+ GB RAM, an SSD, and 2+ USB-A ports will work as a substitute.

### Alternatives

Any Intel N95/N97/N100/N200 mini PC works. Key requirements are 8+ GB RAM (12+ preferred for PostGIS), SSD storage (not eMMC), and at least two USB-A ports for the SDR dongles. Avoid ARM SBCs (Raspberry Pi) — PostgreSQL + PostGIS performance on ARM is significantly worse at this memory tier.

---

## 2. SDR Reception

| Component | Model | Qty | Key Specs | Notes |
|-----------|-------|-----|-----------|-------|
| SDR Dongle | Nooelec NESDR SMArt v5 | 2 | RTL2832U + R820T2, 0.5 PPM TCXO, SMA-F | One per frequency (1090 MHz, 978 MHz). The v5 has the best out-of-box frequency stability. |
| LNA | Nooelec SAWbird+ ADS-B | 1 | Dual-channel (1090 + 978 MHz), ~34dB gain, 0.8dB NF, dual SAW filters per channel | Powers from USB 5V (300mA), bias-tee, or pin header. One source only. |
| Antenna | 1090/978 MHz dual-band fiberglass | 2 | 5dBi gain, N-type female connector | Any ADS-B-specific antenna works. Avoid general-purpose wideband antennas. |
| Cable | N-Male to SMA-Male coaxial | 2 | 10ft / 3m, RG-316 or LMR-195 | Connects antenna N-type to SAWbird+ SMA input. Keep as short as practical. |

### SDR Alternatives

The Nooelec NESDR SMArt v5 is preferred for its 0.5 PPM TCXO (no frequency drift). The RTL-SDR Blog V4 is a solid alternative with similar performance. Avoid the cheapest generic RTL-SDR dongles — they lack TCXOs and drift significantly with temperature, which matters for outdoor deployment.

### LNA Alternatives

The SAWbird+ ADS-B is ideal because it handles both 1090 and 978 MHz in a single device with dedicated SAW filters per channel. If only doing 1090 MHz (no UAT), the single-channel SAWbird+ 1090 is cheaper. Any LNA with a SAW filter in the 1090 MHz band and >20 dB gain will improve reception. Avoid broadband LNAs without SAW filtering — they amplify interference along with signal.

### Antenna Alternatives

The FlightAware 1090 MHz antenna is widely available and performs well. For dual-frequency operation, ensure the antenna covers both 978 and 1090 MHz. A DIY quarter-wave ground plane antenna (spider antenna) works surprisingly well for 1090 MHz and costs essentially nothing to build.

---

## 3. Outdoor Deployment

| Component | Model | Key Specs | Notes |
|-----------|-------|-----------|-------|
| Enclosure | CHENGPI Outdoor Electrical Box | 15.7" × 9.8" × 6", IP65, cold-rolled alloy steel, thermostat fan | Fits N100 + UPS + SAWbird + dongles with room to spare. DIN rail and shelf mounts inside. |
| UPS | Shanqiu 74Wh Mini UPS | 20000mAh, 12V DC output + 5V USB, pass-through charging | 12V direct to N100 (no wall wart). 5V USB powers SAWbird+. ~4 hours runtime on battery. |

The enclosure includes pole-mount hardware (304 stainless steel hoop straps), a 45° sloped roof for rain shedding, and an industrial lock with waterproof sleeve. The thermostat-controlled fan activates automatically based on internal temperature.

### Enclosure Alternatives

Any IP65-rated metal or polycarbonate enclosure with dimensions of at least 12" × 8" × 5" will work. The key requirements are weatherproofing, some form of ventilation (passive or active), and enough interior space for the compute hardware. Avoid all-plastic enclosures in direct sun — they don't dissipate heat well.

### UPS Alternatives

Any 12V DC mini UPS works. The critical feature is 12V DC output (not just AC inverter) — this lets the N100 run directly without a power brick inside the enclosure, reducing heat and component count. 20000mAh provides approximately 4 hours of runtime, which covers most power blips and short outages.

---

## 4. Mounting and Connectivity

| Component | Description | Qty | Notes |
|-----------|-------------|-----|-------|
| Cable glands / grommets | Weatherproof cable entry | 2–4 | For antenna cables and power entry into enclosure |
| Antenna mounting brackets | U-bolts or hose clamps | 2 | For attaching antennas to fence, mast, or railing |
| Ethernet cable (outdoor) | Cat6 shielded, outdoor-rated | 1 | Optional — WiFi is used in this build, but wired is more reliable |

---

## 5. Cost Summary

| Category | Approximate Cost (USD) |
|----------|----------------------|
| Edge computer (N100) | $130–$170 |
| SDR dongles (2×) | $50–$60 |
| SAWbird+ LNA | $35–$45 |
| Antennas (2×) | $30–$50 |
| Coax cables (2×) | $15–$25 |
| Outdoor enclosure | $45–$65 |
| Mini UPS | $35–$50 |
| Mounting hardware | $10–$20 |
| **Total** | **$350–$485** |

Prices as of early 2026. The compute hardware is the largest single cost. If you already have a mini PC or thin client with adequate specs, the RF and deployment components run about $170–$250.

---

## 6. References

| Resource | Description |
|----------|-------------|
| [Signal Chain](signal-chain.md) | How these components connect and the RF path |
| [SDR Configuration](../deployment/03-sdr-configuration.md) | Software setup once hardware is assembled |
| [Nooelec SAWbird+ Datasheet](https://www.nooelec.com/store/sawbird-plus-adsb.html) | LNA specifications |
| [SDR Enthusiasts Ultrafeeder](https://github.com/sdr-enthusiasts/docker-adsb-ultrafeeder) | Docker container for the reception stack |

---

## 7. Document Info

| | |
|---|---|
| Author | VintageDon (https://github.com/vintagedon) |
| Created | 2026-03-17 |
| Version | 1.0 |
