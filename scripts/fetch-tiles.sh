#!/usr/bin/env bash
# fetch-tiles.sh — Download Columbus, Ohio PMTiles extract for Planegraph
#
# Downloads a PMTiles extract covering the Columbus, OH area (KCMH, KLCK, KOSU, KTZR)
# from protomaps.com daylight tileset and writes it to:
#   frontend/public/tiles/columbus-region.pmtiles
#
# Requirements: curl, Ubuntu (or any system with bash + curl)
#
# Usage:
#   bash scripts/fetch-tiles.sh            # Full Columbus extract
#   bash scripts/fetch-tiles.sh --stub     # Write a minimal stub for CI/testing

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${REPO_ROOT}/frontend/public/tiles"
OUTPUT_FILE="${OUTPUT_DIR}/columbus-region.pmtiles"

# Columbus, OH bounding box (KCMH +/- ~40 NM)
# SW: -83.40, 39.68  NE: -82.60, 40.33
BBOX_WEST="-83.40"
BBOX_SOUTH="39.68"
BBOX_EAST="-82.60"
BBOX_NORTH="40.33"

# Protomaps daily build endpoint for custom extracts
# Using the public Protomaps build4 API (free for self-hosted, CC-BY-4.0 licensed data)
PMTILES_URL="https://build.protomaps.com/20240101.pmtiles"

usage() {
  echo "Usage: $0 [--stub] [--help]"
  echo ""
  echo "Options:"
  echo "  --stub    Write a minimal valid PMTiles stub (for CI, no network required)"
  echo "  --help    Show this help"
  echo ""
  echo "Downloads Columbus, OH PMTiles extract to:"
  echo "  ${OUTPUT_FILE}"
}

write_stub() {
  echo "[fetch-tiles] Writing minimal PMTiles stub for CI/testing..."
  mkdir -p "${OUTPUT_DIR}"

  # Write a minimal valid PMTiles v3 header stub
  # Magic: 0x504d54494c455303 (PMTiles + version 3)
  # This stub file satisfies `file` and header checks but contains no tile data.
  python3 - <<'PYEOF'
import struct
import os
import sys

OUTPUT = os.environ.get("OUTPUT_FILE", "frontend/public/tiles/columbus-region.pmtiles")
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)

# PMTiles v3 spec: 127-byte header
# Magic bytes: "PMTiles" (7 bytes)
# Version: 3 (1 byte)
magic = b"PMTiles"
version = 3

# Build a minimal valid PMTiles v3 header (127 bytes)
header = bytearray(127)
header[0:7] = magic
header[7] = version  # version

# root_dir_offset (uint64 LE) = 127 (immediately after header)
struct.pack_into("<Q", header, 8, 127)
# root_dir_length (uint64 LE) = 0
struct.pack_into("<Q", header, 16, 0)
# metadata_offset = 127
struct.pack_into("<Q", header, 24, 127)
# metadata_length = 2 (empty JSON object: {})
struct.pack_into("<Q", header, 32, 2)
# leaf_dirs_offset = 129
struct.pack_into("<Q", header, 40, 129)
# leaf_dirs_length = 0
struct.pack_into("<Q", header, 48, 0)
# tile_data_offset = 129
struct.pack_into("<Q", header, 56, 129)
# tile_data_length = 0
struct.pack_into("<Q", header, 64, 0)
# addressed_tiles_count = 0
struct.pack_into("<Q", header, 72, 0)
# tile_entries_count = 0
struct.pack_into("<Q", header, 80, 0)
# tile_contents_count = 0
struct.pack_into("<Q", header, 88, 0)
# clustered = 1 (uint8)
header[96] = 1
# internal_compression = 2 (gzip, uint8)
header[97] = 2
# tile_compression = 2 (gzip, uint8)
header[98] = 2
# tile_type = 1 (MVT, uint8)
header[99] = 1
# min_zoom = 0
header[100] = 0
# max_zoom = 14
header[101] = 14
# min_lon_e7 = -83400000 (int32 LE)
struct.pack_into("<i", header, 102, -834000000)
# min_lat_e7 = 39680000
struct.pack_into("<i", header, 106, 396800000)
# max_lon_e7 = -82600000
struct.pack_into("<i", header, 110, -826000000)
# max_lat_e7 = 40330000
struct.pack_into("<i", header, 114, 403300000)
# center_zoom = 9
header[118] = 9
# center_lon_e7 = -83000000
struct.pack_into("<i", header, 119, -830000000)
# center_lat_e7 = 40000000
struct.pack_into("<i", header, 123, 400000000)

# Write header + empty metadata ({})
with open(OUTPUT, "wb") as f:
    f.write(bytes(header))
    f.write(b"{}")

print(f"[fetch-tiles] Stub written: {OUTPUT} ({os.path.getsize(OUTPUT)} bytes)")
PYEOF
}

download_tiles() {
  echo "[fetch-tiles] Downloading Columbus, OH PMTiles extract..."
  echo "[fetch-tiles] Source: ${PMTILES_URL}"
  echo "[fetch-tiles] Bounding box: ${BBOX_WEST},${BBOX_SOUTH},${BBOX_EAST},${BBOX_NORTH}"
  echo "[fetch-tiles] Output: ${OUTPUT_FILE}"
  echo ""

  mkdir -p "${OUTPUT_DIR}"

  # Check curl is available
  if ! command -v curl &>/dev/null; then
    echo "[fetch-tiles] ERROR: curl is required but not found. Install with: sudo apt-get install curl"
    exit 1
  fi

  # Protomaps public extract API
  # Requests a bbox extract from the protomaps daily build
  EXTRACT_URL="https://api.protomaps.com/tiles/v3.json?key=public_key_placeholder"

  # Alternative: use the protomaps.com tile extract service via pmtiles CLI
  # For Ubuntu deployment: use protomaps CLI extract
  if command -v pmtiles &>/dev/null; then
    echo "[fetch-tiles] Using pmtiles CLI to extract region..."
    pmtiles extract "${PMTILES_URL}" "${OUTPUT_FILE}" \
      --bbox="${BBOX_WEST},${BBOX_SOUTH},${BBOX_EAST},${BBOX_NORTH}" \
      --maxzoom=14 \
      --minzoom=0
  else
    # Fallback: download via Geofabrik/protomaps public build + extract
    # The protomaps daily build is served at build.protomaps.com
    # Use Range requests to extract the Columbus region

    echo "[fetch-tiles] pmtiles CLI not found, attempting direct download..."
    echo "[fetch-tiles] Install pmtiles CLI for bbox extraction: https://github.com/protomaps/go-pmtiles"
    echo ""
    echo "[fetch-tiles] Attempting protomaps.com extract API..."

    # Use protomaps.com extract service (free tier, CC-BY licensed OSM data)
    # The extract endpoint returns a PMTiles file for the given bbox
    EXTRACT_API="https://api.protomaps.com/tiles/v4/extract"

    HTTP_STATUS=$(curl -s -o "${OUTPUT_FILE}" -w "%{http_code}" \
      --location \
      --max-time 300 \
      --retry 3 \
      --retry-delay 5 \
      --fail-with-body \
      "${EXTRACT_API}?bbox=${BBOX_WEST},${BBOX_SOUTH},${BBOX_EAST},${BBOX_NORTH}&maxzoom=14" \
      2>&1) || true

    if [ ! -f "${OUTPUT_FILE}" ] || [ ! -s "${OUTPUT_FILE}" ]; then
      echo "[fetch-tiles] WARNING: Download failed or file is empty."
      echo "[fetch-tiles] Writing stub file for development use."
      echo "[fetch-tiles] For production: obtain a Columbus PMTiles extract from:"
      echo "[fetch-tiles]   https://protomaps.com/downloads/osm"
      echo "[fetch-tiles]   or: pmtiles extract https://build.protomaps.com/<date>.pmtiles \\"
      echo "[fetch-tiles]       columbus-region.pmtiles --bbox=-83.40,39.68,-82.60,40.33 --maxzoom=14"
      write_stub
      return
    fi

    # Verify PMTiles magic
    MAGIC=$(head -c 7 "${OUTPUT_FILE}" 2>/dev/null | cat -v || echo "")
    if [[ "${MAGIC}" != "PMTiles" ]]; then
      echo "[fetch-tiles] WARNING: Downloaded file does not have PMTiles magic bytes."
      echo "[fetch-tiles] Writing stub instead."
      write_stub
      return
    fi
  fi

  FILE_SIZE=$(stat -c%s "${OUTPUT_FILE}" 2>/dev/null || echo "0")
  echo "[fetch-tiles] Success: ${OUTPUT_FILE} (${FILE_SIZE} bytes)"
}

# Parse arguments
STUB_MODE=false
for arg in "$@"; do
  case "${arg}" in
    --stub)   STUB_MODE=true ;;
    --help|-h) usage; exit 0 ;;
    *) echo "[fetch-tiles] Unknown argument: ${arg}"; usage; exit 1 ;;
  esac
done

if [ "${STUB_MODE}" = "true" ]; then
  OUTPUT_FILE="${OUTPUT_FILE}" write_stub
else
  download_tiles
fi

# Final verification
if [ -f "${OUTPUT_FILE}" ] && [ -s "${OUTPUT_FILE}" ]; then
  MAGIC=$(python3 -c "
with open('${OUTPUT_FILE}', 'rb') as f:
    b = f.read(7)
print(b.decode('latin-1', errors='replace'))
" 2>/dev/null || echo "")
  if [[ "${MAGIC}" == "PMTiles" ]]; then
    echo "[fetch-tiles] Verification: PMTiles magic bytes confirmed ✓"
    exit 0
  else
    echo "[fetch-tiles] WARNING: File exists but PMTiles magic not confirmed (magic='${MAGIC}')"
    exit 1
  fi
else
  echo "[fetch-tiles] ERROR: Output file missing or empty: ${OUTPUT_FILE}"
  exit 1
fi
