"""
config.py — Runtime configuration container for the ingest daemon.

Loads initial values from environment variables and exposes a mutable
Config object that is updated in-place when a config_changed NOTIFY
arrives from PostgreSQL.
"""

import json
import logging
import os

log = logging.getLogger(__name__)


class Config:
    """
    Mutable runtime configuration.  All thresholds are read from
    pipeline_config at startup and updated live by the LISTEN handler.
    """

    def __init__(self):
        # --- database ---
        self.db_dsn: str = (
            f"postgresql://{os.environ['POSTGRES_USER']}"
            f":{os.environ['POSTGRES_PASSWORD']}"
            f"@{os.environ.get('POSTGRES_HOST', 'localhost')}"
            f":{os.environ.get('POSTGRES_PORT', '5432')}"
            f"/{os.environ['POSTGRES_DB']}"
        )

        # --- SBS source ---
        self.sbs_host: str = os.environ.get("SBS_HOST", "localhost")
        self.sbs_port: int = int(os.environ.get("SBS_PORT", "30003"))

        # --- thresholds (overwritten from pipeline_config on startup) ---
        self.session_gap_threshold_sec: int = int(
            os.environ.get("SESSION_GAP_THRESHOLD_SEC", "300")
        )
        self.ground_turnaround_threshold_sec: int = 120
        self.batch_interval_sec: float = float(
            os.environ.get("INGEST_BATCH_INTERVAL_SEC", "2")
        )
        self.phase_classification: dict = {
            "ground_speed_max_kts": 50,
            "ground_alt_agl_max_ft": 200,
            "takeoff_vrate_min_fpm": 200,
            "climb_vrate_min_fpm": 200,
            "cruise_alt_min_ft": 18000,
            "descent_vrate_max_fpm": -200,
            "approach_alt_max_ft": 5000,
            "approach_speed_max_kts": 200,
            "landing_vrate_max_fpm": -100,
            "landing_alt_agl_max_ft": 100,
        }

    def apply_db_row(self, key: str, value) -> None:
        """Apply a single pipeline_config row to in-memory state."""
        try:
            if key == "session_gap_threshold_sec":
                self.session_gap_threshold_sec = int(value)
                log.info("config: session_gap_threshold_sec = %d", self.session_gap_threshold_sec)
            elif key == "ground_turnaround_threshold_sec":
                self.ground_turnaround_threshold_sec = int(value)
                log.info("config: ground_turnaround_threshold_sec = %d", self.ground_turnaround_threshold_sec)
            elif key == "batch_interval_sec":
                self.batch_interval_sec = float(value)
                log.info("config: batch_interval_sec = %.1f", self.batch_interval_sec)
            elif key == "phase_classification":
                if isinstance(value, str):
                    value = json.loads(value)
                self.phase_classification = value
                log.info("config: phase_classification updated")
        except Exception as exc:
            log.warning("config: failed to apply key=%s value=%r: %s", key, value, exc)

    def apply_notify_payload(self, payload: str) -> None:
        """Handle a config_changed NOTIFY payload (JSON string)."""
        try:
            data = json.loads(payload)
            self.apply_db_row(data["key"], data["value"])
        except Exception as exc:
            log.warning("config: failed to parse notify payload %r: %s", payload, exc)
