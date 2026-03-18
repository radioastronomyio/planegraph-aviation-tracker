"""
phase_classifier.py — Fuzzy flight phase classifier.

Assigns one of: GND, TOF, CLB, CRZ, DES, APP, LDG, UNKNOWN
based on threshold config stored in pipeline_config key
'phase_classification'.  Speed and vertical rate are smoothed
with rolling windows before classification.
"""

from __future__ import annotations

from collections import deque
from typing import Optional


PHASES = ("GND", "TOF", "CLB", "CRZ", "DES", "APP", "LDG", "UNKNOWN")

_SPEED_WINDOW  = 5   # samples
_VRATE_WINDOW  = 5   # samples


class PhaseClassifier:
    """
    Stateless classifier.  The caller passes per-aircraft rolling windows
    (speed_window, vrate_window) stored on the SessionState; this class
    only implements the decision logic.
    """

    def __init__(self, cfg: dict):
        self._cfg = cfg

    def update_config(self, cfg: dict) -> None:
        self._cfg = cfg

    def classify(
        self,
        alt_ft:    Optional[int],
        speed_kts: Optional[int],
        vrate_fpm: Optional[int],
        on_ground: bool,
        speed_window: deque,
        vrate_window: deque,
    ) -> str:
        """
        Returns a phase string.  Updates the rolling windows in-place.
        """
        cfg = self._cfg

        # Update rolling windows
        if speed_kts is not None:
            speed_window.append(float(speed_kts))
        if vrate_fpm is not None:
            vrate_window.append(float(vrate_fpm))

        # Compute smoothed values; fall back to raw if window is empty
        spd   = _mean(speed_window)  if speed_window  else (float(speed_kts)  if speed_kts  is not None else None)
        vrate = _mean(vrate_window)  if vrate_window  else (float(vrate_fpm)  if vrate_fpm  is not None else None)
        alt   = float(alt_ft) if alt_ft is not None else None

        if alt is None:
            return "UNKNOWN"

        gnd_spd_max   = cfg.get("ground_speed_max_kts",    50)
        gnd_alt_max   = cfg.get("ground_alt_agl_max_ft",  200)
        tof_vr_min    = cfg.get("takeoff_vrate_min_fpm",   200)
        clb_vr_min    = cfg.get("climb_vrate_min_fpm",     200)
        crz_alt_min   = cfg.get("cruise_alt_min_ft",     18000)
        des_vr_max    = cfg.get("descent_vrate_max_fpm",  -200)
        app_alt_max   = cfg.get("approach_alt_max_ft",    5000)
        app_spd_max   = cfg.get("approach_speed_max_kts",  200)
        ldg_vr_max    = cfg.get("landing_vrate_max_fpm",  -100)
        ldg_alt_max   = cfg.get("landing_alt_agl_max_ft",  100)

        # --- GND: transponder on-ground flag OR very low+slow ---
        if on_ground:
            return "GND"
        if spd is not None and spd < gnd_spd_max and alt < gnd_alt_max:
            return "GND"

        # --- LDG: very low altitude with negative vrate ---
        if alt < ldg_alt_max and vrate is not None and vrate < ldg_vr_max:
            return "LDG"

        # --- TOF: low altitude with strong positive vrate ---
        if alt < gnd_alt_max * 3 and vrate is not None and vrate > tof_vr_min:
            return "TOF"

        # --- APP: below approach altitude, slow, descending ---
        if (
            alt < app_alt_max
            and vrate is not None and vrate < des_vr_max
            and (spd is None or spd < app_spd_max)
        ):
            return "APP"

        # --- CLB: strong positive vertical rate ---
        if vrate is not None and vrate > clb_vr_min:
            return "CLB"

        # --- DES: strong negative vertical rate ---
        if vrate is not None and vrate < des_vr_max:
            return "DES"

        # --- CRZ: high altitude, roughly level ---
        if alt >= crz_alt_min:
            return "CRZ"

        # --- fallback for mid-altitude level flight ---
        if vrate is not None and des_vr_max <= vrate <= clb_vr_min:
            return "CRZ"

        return "UNKNOWN"


def make_speed_window() -> deque:
    return deque(maxlen=_SPEED_WINDOW)


def make_vrate_window() -> deque:
    return deque(maxlen=_VRATE_WINDOW)


def _mean(d: deque) -> float:
    return sum(d) / len(d)
