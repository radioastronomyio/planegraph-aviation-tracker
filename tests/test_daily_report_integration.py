"""
Integration test: generate a report for the most recent full day of data.
Run on edge02 only:
    python -m pytest tests/test_daily_report_integration.py -v -s
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live-DB integration test skipped",
)

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "daily_report.py"


def test_generate_report_for_yesterday():
    """Generate yesterday's report and verify the PDF exists and is >50KB."""
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--date", yesterday,
         "--output-dir", "/tmp/planegraph-test-reports"],
        capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, f"Script failed: {result.stderr}"

    year, month, _ = yesterday.split("-")
    pdf_path = f"/tmp/planegraph-test-reports/{year}/{month}/planegraph-daily-{yesterday}.pdf"
    assert os.path.exists(pdf_path), f"PDF not created at {pdf_path}"

    size = os.path.getsize(pdf_path)
    assert size > 50_000, f"PDF suspiciously small: {size} bytes"
    print(f"Generated: {pdf_path} ({size:,} bytes)")
