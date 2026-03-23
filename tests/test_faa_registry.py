"""
Unit tests for tools/faa_registry_refresh.py

    cd /opt/planegraph/repo/planegraph-aviation-tracker
    source /opt/planegraph/venv/bin/activate
    python -m pytest tests/test_faa_registry.py -v
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from faa_registry_refresh import (
    classify_fleet_category,
    mode_s_to_hex,
    parse_master,
    _zip_is_stale,
)


# ---------------------------------------------------------------------------
# 1. MODE_S_CODE → hex conversion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode_s,expected", [
    ("10742937", "A3EC99"),   # 10742937 decimal → 0xA3EC99 (spec example had wrong hex)
    ("1",        "000001"),   # pad to 6 chars
    ("",         None),       # empty → skip
    ("abc",      None),       # non-numeric → skip
    ("  ",       None),       # whitespace → skip
])
def test_mode_s_to_hex_conversion(mode_s, expected):
    assert mode_s_to_hex(mode_s) == expected


# ---------------------------------------------------------------------------
# 2. Fleet category classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("owner,acft_type,engine_type,weight_class,expected", [
    ("SOUTHWEST AIRLINES CO", "Fixed Wing Multi-Engine", "Turbo-Fan", "CLASS 3", "Commercial"),
    ("DELTA AIR LINES INC",   "Fixed Wing Multi-Engine", "Turbo-Fan", "CLASS 4", "Commercial"),
    ("SMITH, JOHN A",         "Fixed Wing Single-Engine", "Reciprocating", "CLASS 1", "GA"),
    ("DOE, JANE M",           "Fixed Wing Single-Engine", "Reciprocating", "CLASS 2", "GA"),
    ("FEDERAL EXPRESS CORP",  "Fixed Wing Multi-Engine", "Turbo-Fan", "CLASS 4", "Cargo"),
    ("UNITED PARCEL SERVICE", "Fixed Wing Multi-Engine", "Turbo-Fan", "CLASS 4", "Cargo"),
    ("ACME CORP LLC",         "Rotorcraft", "Turbo-Shaft", "CLASS 2", "Unknown"),
])
def test_fleet_category_classification(owner, acft_type, engine_type, weight_class, expected):
    result = classify_fleet_category(owner, acft_type, engine_type, weight_class)
    assert result == expected, f"owner={owner!r}: expected {expected!r}, got {result!r}"


# ---------------------------------------------------------------------------
# 3. MASTER.txt parsing — pipe-delimited with trailing commas
# ---------------------------------------------------------------------------

SAMPLE_MASTER = (
    "N-NUMBER|SERIAL NUMBER|MFR MDL CODE|ENG MFR MDL|YEAR MFR|TYPE REGISTRANT|"
    "NAME|STREET|STREET2|CITY|STATE|ZIP CODE|REGION|COUNTY|COUNTRY|"
    "LAST ACTION DATE|CERT ISSUE DATE|CERTIFICATION|TYPE AIRCRAFT|TYPE ENGINE|"
    "STATUS CODE|MODE S CODE|FRACT OWNER|AIR WORTH DATE|OTHER NAMES(1)|"
    "OTHER NAMES(2)|OTHER NAMES(3)|OTHER NAMES(4)|OTHER NAMES(5)|"
    "EXPIRATION DATE|UNIQUE ID|KIT MFR|KIT MODEL|MODE S CODE HEX|\n"
    "551CP |12345   |7104433|12345|2005|1|SMITH, JOHN A|123 MAIN ST||COLUMBUS|OH|43215|"
    "5|049|US|20230101|20050601|S|4|1|V|10742937||20050601|||||||||20261231|1234567|||\n"
    "123AB |67890   |7210521|67890|2010|2|DELTA AIR LINES INC|PO BOX 1||ATLANTA|GA|30320|"
    "3|121|US|20230201|20100301|1,2|5|5|V|10000001||20100301|||||||||20261231|7654321|||\n"
    "   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |"
    "   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |\n"
)


def test_master_file_parsing():
    """Parse a 5-line (2 data) MASTER.txt sample, verify field extraction."""
    rows = parse_master(SAMPLE_MASTER.encode("latin-1"))

    # Should have 3 rows (including the blank one; the blank may or may not be returned)
    # At minimum we need the 2 valid rows
    valid = [r for r in rows if r.get("N-NUMBER", "").strip()]
    assert len(valid) >= 2

    r0 = valid[0]
    assert r0["N-NUMBER"] == "551CP"
    assert r0["MODE S CODE"] == "10742937"
    assert r0["NAME"] == "SMITH, JOHN A"
    assert r0["STATE"] == "OH"

    r1 = valid[1]
    assert r1["N-NUMBER"] == "123AB"
    assert r1["MODE S CODE"] == "10000001"
    assert r1["NAME"] == "DELTA AIR LINES INC"


# ---------------------------------------------------------------------------
# 4. --skip-download uses cached ZIP without HTTP request
# ---------------------------------------------------------------------------

def test_skip_download_flag(tmp_path):
    """--skip-download must not call urllib.request.urlretrieve."""
    zip_path = tmp_path / "ReleasableAircraft.zip"
    zip_path.write_bytes(b"fake zip data")

    import faa_registry_refresh as faa

    with patch("faa_registry_refresh.run_etl"), \
         patch("urllib.request.urlretrieve") as mock_dl:

        original_main = faa.main

        def patched_main():
            with patch("sys.argv", ["faa_registry_refresh.py", "--skip-download", "--cache-dir", str(tmp_path)]), \
                 patch.dict(os.environ, {"DATABASE_URL": "postgresql://x:y@localhost/db"}):
                original_main()

        patched_main()

        mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Missing DATABASE_URL → exit code 3
# ---------------------------------------------------------------------------

def test_missing_database_url():
    """Script exits with code 3 when DATABASE_URL is unset."""
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)

    script = Path(__file__).parent.parent / "tools" / "faa_registry_refresh.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3
    assert "DATABASE_URL" in result.stderr


# ---------------------------------------------------------------------------
# 6. Stale cache detection
# ---------------------------------------------------------------------------

def test_stale_cache_detection(tmp_path):
    """A ZIP older than 7 days triggers re-download (is stale)."""
    zip_path = tmp_path / "ReleasableAircraft.zip"
    zip_path.write_bytes(b"old data")

    # Set mtime to 8 days ago
    old_mtime = time.time() - 8 * 86400
    os.utime(zip_path, (old_mtime, old_mtime))

    assert _zip_is_stale(zip_path) is True


def test_fresh_cache_not_stale(tmp_path):
    """A ZIP newer than 7 days is not stale."""
    zip_path = tmp_path / "ReleasableAircraft.zip"
    zip_path.write_bytes(b"new data")
    # mtime is now — not stale
    assert _zip_is_stale(zip_path) is False
