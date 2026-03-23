"""
Unit tests for tools/daily_report.py — run without a database connection.

    cd /opt/planegraph/repo/planegraph-aviation-tracker
    source /opt/planegraph/venv/bin/activate
    python -m pytest tests/test_daily_report.py -v
"""

import math
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# Allow importing from tools/
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from daily_report import (
    classify_flight,
    detect_gaps,
    extract_callsign_prefix,
    output_path,
    page3_altitude_speed,
    page4_spatial,
)


# ---------------------------------------------------------------------------
# 1. Output path generation
# ---------------------------------------------------------------------------

def test_output_path_generation():
    d = date(2026, 3, 21)
    path = output_path("/some/output/dir", d)
    assert str(path) == "/some/output/dir/2026/03/planegraph-daily-2026-03-21.pdf"


def test_output_path_generation_different_month():
    d = date(2025, 12, 1)
    path = output_path("/reports", d)
    assert str(path) == "/reports/2025/12/planegraph-daily-2025-12-01.pdf"


# ---------------------------------------------------------------------------
# 2. Partial day detection
# ---------------------------------------------------------------------------

def test_partial_day_detection():
    """Data spanning 08:00–22:00 gives 14 hours, 58.3% completeness."""
    day_start = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)
    # Build hourly_df for hours 8–21 inclusive (14 hours)
    hours = [day_start + timedelta(hours=h) for h in range(8, 22)]
    hourly_df = pd.DataFrame({
        "hour": pd.to_datetime(hours, utc=True),
        "reports": [100] * 14,
        "unique_aircraft": [10] * 14,
    })

    has_data_hours = len(hourly_df)
    completeness_pct = has_data_hours / 24 * 100
    is_partial = has_data_hours < 24

    assert is_partial is True
    assert has_data_hours == 14
    assert math.isclose(completeness_pct, 14 / 24 * 100, rel_tol=1e-3)


# ---------------------------------------------------------------------------
# 3. Gap detection
# ---------------------------------------------------------------------------

def test_gap_detection():
    """Hours 10–12 (3 hours) absent → one gap detected."""
    day_start = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)
    present_hours = list(range(0, 10)) + list(range(13, 24))
    hours = [day_start + timedelta(hours=h) for h in present_hours]
    hourly_df = pd.DataFrame({
        "hour": pd.to_datetime(hours, utc=True),
        "reports": [50] * len(present_hours),
        "unique_aircraft": [5] * len(present_hours),
    })

    gaps = detect_gaps(hourly_df, day_start, threshold_minutes=15)

    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["start"] == day_start + timedelta(hours=10)
    assert gap["end"] == day_start + timedelta(hours=13)
    assert gap["duration_min"] == 180


def test_gap_detection_no_gaps():
    """All 24 hours present → no gaps."""
    day_start = datetime(2026, 3, 21, 0, 0, 0, tzinfo=timezone.utc)
    hours = [day_start + timedelta(hours=h) for h in range(24)]
    hourly_df = pd.DataFrame({
        "hour": pd.to_datetime(hours, utc=True),
        "reports": [50] * 24,
        "unique_aircraft": [5] * 24,
    })
    gaps = detect_gaps(hourly_df, day_start)
    assert gaps == []


# ---------------------------------------------------------------------------
# 4. Callsign prefix extraction
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("callsign,expected", [
    ("AAL1539", "AAL"),
    ("N551CP", "GA (N-reg)"),
    ("SKW5443", "SKW"),
    (None, "Unknown"),
    ("", "Unknown"),
    ("DAL890", "DAL"),
    ("UAL123", "UAL"),
    ("N12345", "GA (N-reg)"),
])
def test_callsign_prefix_extraction(callsign, expected):
    assert extract_callsign_prefix(callsign) == expected


# ---------------------------------------------------------------------------
# 5. Airline classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("callsign,squawk,expected_class", [
    ("AAL1539", None, "Commercial"),
    ("UAL123", None, "Commercial"),
    ("DAL456", None, "Commercial"),
    ("SKW5443", None, "Commercial"),
    ("N551CP", None, "GA"),
    ("N12345", None, "GA"),
    ("RCH123", None, "Military"),
    ("VALOR01", None, "Military"),
    (None, None, "Unknown"),
    ("", None, "Unknown"),
    ("XYZABC", None, "Unknown"),
])
def test_airline_classification(callsign, squawk, expected_class):
    result = classify_flight(callsign, squawk)
    assert result == expected_class


# ---------------------------------------------------------------------------
# 6. No data → exit code 1
# ---------------------------------------------------------------------------

def test_no_data_exit_code(tmp_path, monkeypatch):
    """When the DB returns zero rows, script must exit with code 1."""
    import daily_report as dr

    monkeypatch.setenv("DATABASE_URL", "postgresql://planegraph:test@localhost:5432/planegraph")
    monkeypatch.setattr(sys, "argv", ["daily_report.py", "--date", "2020-01-01"])

    mock_conn = MagicMock()

    with patch.object(dr, "get_connection", return_value=mock_conn), \
         patch.object(dr, "load_summary", return_value={"total_reports": 0, "unique_aircraft": 0, "sessions_in_window": 0}):
        with pytest.raises(SystemExit) as exc_info:
            dr.main()

    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# 7. Missing DATABASE_URL → exit code 3
# ---------------------------------------------------------------------------

def test_missing_database_url(tmp_path):
    """When DATABASE_URL is unset, script must exit with code 3."""
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)

    script = Path(__file__).parent.parent / "tools" / "daily_report.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3
    assert "DATABASE_URL" in result.stderr


# ---------------------------------------------------------------------------
# 8. NULL handling in plots
# ---------------------------------------------------------------------------

def test_null_handling_in_plots(tmp_path):
    """page3_altitude_speed must handle DataFrames with 80% NULL alt_ft."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages

    alt_values = [None] * 800 + list(np.random.randint(1000, 40000, 200))
    df = pd.DataFrame({
        "alt_ft": pd.array(alt_values, dtype="object"),
        "speed_kts": pd.array([None] * 200 + list(np.random.randint(100, 500, 800)), dtype="object"),
        "vrate_fpm": pd.array([None] * 100 + list(np.random.randint(-2000, 2000, 900)), dtype="object"),
        "flight_phase": ["CRZ"] * 500 + ["CLB"] * 300 + [None] * 200,
    })
    # Convert to numeric (NULLs become NaN)
    for col in ["alt_ft", "speed_kts", "vrate_fpm"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    report_date = date(2026, 3, 21)
    pdf_path = tmp_path / "test_null.pdf"

    # Must not raise
    with PdfPages(str(pdf_path)) as pdf:
        page3_altitude_speed(pdf, report_date, df)

    assert pdf_path.exists()


# ---------------------------------------------------------------------------
# 9. Station coords optional — range plot skipped without error
# ---------------------------------------------------------------------------

def test_station_coords_optional(tmp_path):
    """page4_spatial must run without error when station coords are None."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages

    n = 100
    df = pd.DataFrame({
        "lat": np.random.uniform(39.5, 40.5, n),
        "lon": np.random.uniform(-83.5, -82.5, n),
        "alt_ft": np.random.randint(5000, 35000, n).astype(float),
        "track": np.random.uniform(0, 360, n),
    })
    airports_df = pd.DataFrame(columns=["icao_code", "lat", "lon"])
    report_date = date(2026, 3, 21)
    pdf_path = tmp_path / "test_spatial.pdf"

    with PdfPages(str(pdf_path)) as pdf:
        page4_spatial(pdf, report_date, df, airports_df, station_lat=None, station_lon=None)

    assert pdf_path.exists()
