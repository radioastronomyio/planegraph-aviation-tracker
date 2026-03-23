#!/usr/bin/env python3
"""
FAA Aircraft Registry ETL

Downloads the FAA ReleasableAircraft.zip, parses MASTER.txt and ACFTREF.txt,
and upserts the joined data into the aircraft_registry table.

Usage:
    python tools/faa_registry_refresh.py                    # download + refresh
    python tools/faa_registry_refresh.py --skip-download    # refresh from cached ZIP
    python tools/faa_registry_refresh.py --force            # force re-download
"""

import argparse
import csv
import io
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

FAA_ZIP_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
DEFAULT_CACHE_DIR = "/opt/planegraph/cache/faa"
CACHE_MAX_AGE_DAYS = 7

# ---------------------------------------------------------------------------
# Hex conversion
# ---------------------------------------------------------------------------

def mode_s_to_hex(mode_s_code: str) -> str | None:
    """Convert FAA MODE_S_CODE decimal string to 6-char uppercase hex.

    Returns None if the input is empty or non-numeric.
    """
    if not mode_s_code or not mode_s_code.strip():
        return None
    try:
        val = int(mode_s_code.strip())
    except ValueError:
        return None
    return format(val, "06X")


# ---------------------------------------------------------------------------
# Fleet category classification
# ---------------------------------------------------------------------------

AIRLINE_KEYWORDS = {
    "AIRLINES", "AIRWAYS", "SOUTHWEST", "DELTA", "UNITED", "AMERICAN",
    "JETBLUE", "ALASKA", "FRONTIER", "SPIRIT", "REPUBLIC", "SKYWEST",
    "ENVOY", "PSA", "MESA", "ENDEAVOR", "FEDEX", "UPS",
}

CARGO_KEYWORDS = {
    "FEDEX", "FEDERAL EXPRESS", "UPS", "UNITED PARCEL", "ATLAS AIR",
    "KALITTA", "ABX AIR",
}

TURBO_FAN_KEYWORDS = {"TURBO-FAN", "TURBO FAN"}
HEAVY_WEIGHT_CLASSES = {"CLASS 3", "CLASS 4"}
LIGHT_WEIGHT_CLASSES = {"CLASS 1", "CLASS 2"}


def classify_fleet_category(
    owner_name: str,
    aircraft_type: str,
    engine_type: str,
    weight_class: str,
) -> str:
    """Deterministic fleet category from registry fields."""
    owner_upper = (owner_name or "").upper()
    at_upper = (aircraft_type or "").upper()
    et_upper = (engine_type or "").upper()
    wc_upper = (weight_class or "").upper()

    # Cargo first (subset of potential Commercial hits)
    for kw in CARGO_KEYWORDS:
        if kw in owner_upper:
            return "Cargo"

    # Commercial: airline keyword OR turbofan heavy corp
    for kw in AIRLINE_KEYWORDS:
        if kw in owner_upper:
            return "Commercial"
    is_turbofan = any(kw in et_upper for kw in TURBO_FAN_KEYWORDS)
    is_heavy = wc_upper in HEAVY_WEIGHT_CLASSES
    # Heuristic for corporate: no comma in owner name (individuals have "LAST, FIRST")
    is_corp = "," not in owner_upper and len(owner_upper) > 2
    if is_turbofan and is_heavy and is_corp:
        return "Commercial"

    # GA: fixed wing light, individual owner
    is_fixed_wing = "FIXED WING" in at_upper
    is_light = wc_upper in LIGHT_WEIGHT_CLASSES
    is_individual = "," in owner_upper
    if is_fixed_wing and is_light and is_individual:
        return "GA"

    return "Unknown"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# FAA MASTER.txt columns (pipe-delimited, trailing pipe + comma)
MASTER_COLS = [
    "N-NUMBER", "SERIAL NUMBER", "MFR MDL CODE", "ENG MFR MDL",
    "YEAR MFR", "TYPE REGISTRANT", "NAME", "STREET", "STREET2",
    "CITY", "STATE", "ZIP CODE", "REGION", "COUNTY", "COUNTRY",
    "LAST ACTION DATE", "CERT ISSUE DATE", "CERTIFICATION",
    "TYPE AIRCRAFT", "TYPE ENGINE", "STATUS CODE", "MODE S CODE",
    "FRACT OWNER", "AIR WORTH DATE", "OTHER NAMES(1)", "OTHER NAMES(2)",
    "OTHER NAMES(3)", "OTHER NAMES(4)", "OTHER NAMES(5)",
    "EXPIRATION DATE", "UNIQUE ID", "KIT MFR", "KIT MODEL", "MODE S CODE HEX",
]

# FAA ACFTREF.txt columns
ACFTREF_COLS = [
    "CODE", "MFR", "MODEL", "TYPE ACFT", "TYPE ENG",
    "AC CAT", "BUILD CERT IND", "NO ENG", "NO SEATS",
    "AC WEIGHT", "SPEED", "TC DATA SHEET", "TC DATA HOLDER",
    "TC SERIES", "TC ALTERNATE", "TC SERIES IMG URL",
    "TC SERIES ADDL", "TC SERIES ADDL IMG URL",
    "TYPE REGISTRANT",
]

AIRCRAFT_TYPE_MAP = {
    "1": "Glider",
    "2": "Balloon",
    "3": "Blimp/Dirigible",
    "4": "Fixed Wing Single-Engine",
    "5": "Fixed Wing Multi-Engine",
    "6": "Rotorcraft",
    "7": "Weight-Shift-Control",
    "8": "Powered Parachute",
    "9": "Gyroplane",
    "H": "Hybrid Lift",
    "O": "Other",
}

ENGINE_TYPE_MAP = {
    "0": "None",
    "1": "Reciprocating",
    "2": "Turbo-Prop",
    "3": "Turbo-Shaft",
    "4": "Turbo-Jet",
    "5": "Turbo-Fan",
    "6": "Ramjet",
    "7": "2 Cycle",
    "8": "4 Cycle",
    "9": "Unknown",
    "10": "Electric",
    "11": "Rotary",
}

WEIGHT_CLASS_MAP = {
    "CLASS 1": "CLASS 1",
    "CLASS 2": "CLASS 2",
    "CLASS 3": "CLASS 3",
    "CLASS 4": "CLASS 4",
    "1": "CLASS 1",
    "2": "CLASS 2",
    "3": "CLASS 3",
    "4": "CLASS 4",
}


def _parse_pipe_file(data: bytes, expected_cols: list[str]) -> list[dict]:
    """Parse a FAA pipe-delimited file with trailing pipe/comma."""
    text = data.decode("latin-1", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter="|")
    rows = []
    header_found = False
    col_indices = {}

    for raw_row in reader:
        # Strip all fields
        row = [f.strip() for f in raw_row]
        # Remove empty trailing fields (from trailing pipe/comma)
        while row and row[-1] == "":
            row.pop()

        if not row:
            continue

        if not header_found:
            # First non-empty row is the header
            header = [h.strip() for h in row]
            # Build index map for expected columns
            for col in expected_cols:
                for i, h in enumerate(header):
                    if h.upper() == col.upper():
                        col_indices[col] = i
                        break
            header_found = True
            continue

        record = {}
        for col, idx in col_indices.items():
            record[col] = row[idx] if idx < len(row) else ""
        rows.append(record)

    return rows


def parse_master(data: bytes) -> list[dict]:
    return _parse_pipe_file(data, MASTER_COLS)


def parse_acftref(data: bytes) -> list[dict]:
    return _parse_pipe_file(data, ACFTREF_COLS)


# ---------------------------------------------------------------------------
# Download / cache
# ---------------------------------------------------------------------------

def _zip_is_stale(zip_path: Path) -> bool:
    """Return True if ZIP is older than CACHE_MAX_AGE_DAYS."""
    age_seconds = time.time() - zip_path.stat().st_mtime
    return age_seconds > CACHE_MAX_AGE_DAYS * 86400


def download_zip(cache_dir: Path, force: bool = False) -> Path:
    """Download FAA ZIP to cache_dir. Returns path to ZIP file."""
    import urllib.request

    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "ReleasableAircraft.zip"

    if zip_path.exists() and not force and not _zip_is_stale(zip_path):
        print(f"[cache] Using cached ZIP: {zip_path}")
        return zip_path

    print(f"[download] Fetching {FAA_ZIP_URL} ...")
    try:
        urllib.request.urlretrieve(FAA_ZIP_URL, zip_path)
        print(f"[download] Saved to {zip_path} ({zip_path.stat().st_size // 1024 // 1024} MB)")
    except Exception as exc:
        print(f"ERROR: Download failed: {exc}", file=sys.stderr)
        sys.exit(1)

    return zip_path


# ---------------------------------------------------------------------------
# Database upsert
# ---------------------------------------------------------------------------

UPSERT_SQL = """
INSERT INTO aircraft_registry (
    hex, n_number, manufacturer, model, aircraft_type,
    engine_type, engine_count, weight_class,
    owner_name, owner_city, owner_state,
    fleet_category, updated_at
) VALUES %s
ON CONFLICT (hex) DO UPDATE SET
    n_number = EXCLUDED.n_number,
    manufacturer = EXCLUDED.manufacturer,
    model = EXCLUDED.model,
    aircraft_type = EXCLUDED.aircraft_type,
    engine_type = EXCLUDED.engine_type,
    engine_count = EXCLUDED.engine_count,
    weight_class = EXCLUDED.weight_class,
    owner_name = EXCLUDED.owner_name,
    owner_city = EXCLUDED.owner_city,
    owner_state = EXCLUDED.owner_state,
    fleet_category = EXCLUDED.fleet_category,
    updated_at = EXCLUDED.updated_at
"""

BATCH_SIZE = 5000


def upsert_registry(conn, records: list[dict]) -> int:
    """Batch-upsert records into aircraft_registry. Returns rows upserted."""
    now = datetime.now(timezone.utc)
    total_upserted = 0

    with conn.cursor() as cur:
        batch = []
        for rec in records:
            batch.append((
                rec["hex"],
                rec.get("n_number") or None,
                rec.get("manufacturer") or None,
                rec.get("model") or None,
                rec.get("aircraft_type") or None,
                rec.get("engine_type") or None,
                rec.get("engine_count") or None,
                rec.get("weight_class") or None,
                rec.get("owner_name") or None,
                rec.get("owner_city") or None,
                rec.get("owner_state") or None,
                rec["fleet_category"],
                now,
            ))
            if len(batch) >= BATCH_SIZE:
                psycopg2.extras.execute_values(cur, UPSERT_SQL, batch)
                total_upserted += len(batch)
                batch = []

        if batch:
            psycopg2.extras.execute_values(cur, UPSERT_SQL, batch)
            total_upserted += len(batch)

    conn.commit()
    return total_upserted


# ---------------------------------------------------------------------------
# Main ETL logic
# ---------------------------------------------------------------------------

def build_records(master_rows: list[dict], acftref_rows: list[dict]) -> list[dict]:
    """Join MASTER + ACFTREF and build registry records."""
    # Build ACFTREF lookup by CODE
    acftref_by_code: dict[str, dict] = {}
    for row in acftref_rows:
        code = row.get("CODE", "").strip()
        if code:
            acftref_by_code[code] = row

    records = []
    skipped = 0

    for master in master_rows:
        mode_s = master.get("MODE S CODE", "").strip()
        hex_code = mode_s_to_hex(mode_s)
        if not hex_code:
            skipped += 1
            continue

        mfr_mdl_code = master.get("MFR MDL CODE", "").strip()
        acft = acftref_by_code.get(mfr_mdl_code, {})

        # Map type codes to human-readable strings
        aircraft_type_code = acft.get("TYPE ACFT", "").strip()
        aircraft_type = AIRCRAFT_TYPE_MAP.get(aircraft_type_code, aircraft_type_code or None)

        engine_type_code = acft.get("TYPE ENG", "").strip()
        engine_type = ENGINE_TYPE_MAP.get(engine_type_code, engine_type_code or None)

        try:
            engine_count = int(acft.get("NO ENG", "").strip())
        except (ValueError, TypeError):
            engine_count = None

        raw_weight = acft.get("AC WEIGHT", "").strip().upper()
        weight_class = WEIGHT_CLASS_MAP.get(raw_weight, raw_weight or None)

        owner_name = master.get("NAME", "").strip() or None
        owner_city = master.get("CITY", "").strip() or None
        owner_state = master.get("STATE", "").strip() or None
        n_number = master.get("N-NUMBER", "").strip() or None
        manufacturer = acft.get("MFR", "").strip() or master.get("MFR MDL CODE", "").strip() or None
        model = acft.get("MODEL", "").strip() or None

        fleet_category = classify_fleet_category(
            owner_name or "",
            aircraft_type or "",
            engine_type or "",
            weight_class or "",
        )

        records.append({
            "hex": hex_code,
            "n_number": n_number,
            "manufacturer": manufacturer,
            "model": model,
            "aircraft_type": aircraft_type,
            "engine_type": engine_type,
            "engine_count": engine_count,
            "weight_class": weight_class,
            "owner_name": owner_name,
            "owner_city": owner_city,
            "owner_state": owner_state,
            "fleet_category": fleet_category,
        })

    return records, skipped


def run_etl(zip_path: Path, database_url: str) -> None:
    t0 = time.time()
    print(f"[etl] Opening ZIP: {zip_path}")

    with zipfile.ZipFile(zip_path) as zf:
        # Case-insensitive search for MASTER.txt and ACFTREF.txt
        names = {n.upper(): n for n in zf.namelist()}
        master_name = names.get("MASTER.txt".upper()) or names.get("ReleasableAircraft/MASTER.txt".upper())
        acftref_name = names.get("ACFTREF.txt".upper()) or names.get("ReleasableAircraft/ACFTREF.txt".upper())

        if not master_name:
            # Try prefix search
            for name in zf.namelist():
                if name.upper().endswith("MASTER.TXT"):
                    master_name = name
                    break
        if not acftref_name:
            for name in zf.namelist():
                if name.upper().endswith("ACFTREF.TXT"):
                    acftref_name = name
                    break

        if not master_name or not acftref_name:
            print(f"ERROR: Could not find MASTER.txt or ACFTREF.txt in ZIP. Contents: {zf.namelist()}", file=sys.stderr)
            sys.exit(1)

        print(f"[etl] Parsing {master_name} ...")
        master_data = zf.read(master_name)
        master_rows = parse_master(master_data)
        print(f"[etl] {len(master_rows):,} MASTER rows parsed")

        print(f"[etl] Parsing {acftref_name} ...")
        acftref_data = zf.read(acftref_name)
        acftref_rows = parse_acftref(acftref_data)
        print(f"[etl] {len(acftref_rows):,} ACFTREF rows parsed")

    print("[etl] Building registry records (JOIN + classify) ...")
    records, skipped = build_records(master_rows, acftref_rows)
    print(f"[etl] {len(records):,} records built, {skipped:,} skipped (no MODE_S_CODE)")

    print("[db] Connecting ...")
    try:
        conn = psycopg2.connect(database_url)
    except Exception as exc:
        print(f"ERROR: Database connection failed: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        print(f"[db] Upserting {len(records):,} records in batches of {BATCH_SIZE} ...")
        upserted = upsert_registry(conn, records)
        elapsed = time.time() - t0
        print(f"[db] Done. Rows upserted: {upserted:,}. Duration: {elapsed:.1f}s")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="FAA Aircraft Registry ETL")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use previously downloaded ZIP (no HTTP request).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if cached ZIP is recent.",
    )
    parser.add_argument(
        "--cache-dir",
        default=DEFAULT_CACHE_DIR,
        help=f"Directory for downloaded ZIP. Default: {DEFAULT_CACHE_DIR}",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(3)

    cache_dir = Path(args.cache_dir)

    if args.skip_download:
        zip_path = cache_dir / "ReleasableAircraft.zip"
        if not zip_path.exists():
            print(f"ERROR: --skip-download specified but no ZIP found at {zip_path}", file=sys.stderr)
            sys.exit(1)
        print(f"[cache] Using existing ZIP: {zip_path}")
    else:
        zip_path = download_zip(cache_dir, force=args.force)

    run_etl(zip_path, database_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
