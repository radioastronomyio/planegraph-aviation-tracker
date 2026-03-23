#!/usr/bin/env python3
"""
Planegraph Daily Station Report Generator (v2)

Generates a 12-page print-friendly PDF summarizing the previous day's ADS-B data.
Light theme, one insight per page, contextily OSM basemaps, FAA registry enrichment.

Usage:
    python tools/daily_report.py
    python tools/daily_report.py --date 2026-03-22
    python tools/daily_report.py --date 2026-03-22 --station-lat 39.96 --station-lon -82.99
"""

import argparse
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.dates
import numpy as np
import pandas as pd
import psycopg2
from matplotlib.backends.backend_pdf import PdfPages

# ---------------------------------------------------------------------------
# Constants — light theme
# ---------------------------------------------------------------------------

LIGHT_BG = "#ffffff"
PANEL_BG = "#f8f9fa"
ACCENT = "#dc3545"          # Planegraph red
TEXT_COLOR = "#212529"
GRID_COLOR = "#dee2e6"
HIGHLIGHT = "#fd7e14"       # amber
BLUE = "#0d6efd"
GREEN = "#198754"
PURPLE = "#6f42c1"

EDT_OFFSET = -4  # UTC-4 in March (EDT)

# Columbus-area airports for map overlays
COLUMBUS_AIRPORTS = [
    {"icao_code": "KCMH", "lat": 39.9980, "lon": -82.8919},
    {"icao_code": "KLCK", "lat": 39.8138, "lon": -82.9277},
    {"icao_code": "KOSU", "lat": 40.0798, "lon": -83.0730},
    {"icao_code": "KTZR", "lat": 39.9017, "lon": -83.1370},
]

MAP_EXTENT = (-84.5, -82.0, 39.5, 40.8)  # lon_min, lon_max, lat_min, lat_max

AIRLINE_PREFIXES = {
    "AAL", "UAL", "DAL", "SWA", "SKW", "JBU", "ASA", "FFT", "RPA", "ENY",
    "NKS", "FDX", "UPS", "WN", "B6", "NK", "F9", "G4", "SY", "HA",
    "VX", "WS", "AC", "WJA", "EJA", "XJT", "PDT", "OO",
}

MILITARY_PREFIXES = {
    "RCH", "VALOR", "VADOR", "TOPCT", "ARMY", "NAVY", "USAF", "AFSOC",
    "REACH", "KNIFE", "EAGLE", "HAWK", "VIPER", "GHOST", "COBRA",
    "EVAC", "MEDIC", "BOXER", "ATLAS", "IRON", "STEEL",
}

PHASE_COLORS = {
    "CLB": GREEN,
    "CRZ": BLUE,
    "DES": ACCENT,
    "APP": HIGHLIGHT,
    "GND": "#6c757d",
    "TOF": PURPLE,
    "LDG": "#e67e22",
    "UNKNOWN": "#adb5bd",
}


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def apply_light_style():
    plt.rcParams.update({
        "figure.facecolor": LIGHT_BG,
        "axes.facecolor": PANEL_BG,
        "axes.edgecolor": GRID_COLOR,
        "axes.labelcolor": TEXT_COLOR,
        "axes.titlecolor": TEXT_COLOR,
        "xtick.color": TEXT_COLOR,
        "ytick.color": TEXT_COLOR,
        "text.color": TEXT_COLOR,
        "grid.color": GRID_COLOR,
        "grid.alpha": 0.6,
        "legend.facecolor": LIGHT_BG,
        "legend.edgecolor": GRID_COLOR,
        "legend.labelcolor": TEXT_COLOR,
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.labelsize": 9,
        "figure.dpi": 150,
    })


def add_page_header(fig, report_date: date, title: str, page_num: int, total_pages: int = 12):
    """Consistent header banner — light theme."""
    fig.text(
        0.01, 0.975,
        f"PLANEGRAPH  |  {title}",
        fontsize=12, fontweight="bold", color=ACCENT,
        va="top", ha="left",
        transform=fig.transFigure,
    )
    fig.text(
        0.99, 0.975,
        f"{report_date.strftime('%Y-%m-%d')} UTC  |  {page_num}/{total_pages}",
        fontsize=9, color=TEXT_COLOR,
        va="top", ha="right",
        transform=fig.transFigure,
    )
    line = plt.Line2D(
        [0.01, 0.99], [0.960, 0.960],
        transform=fig.transFigure,
        color=ACCENT, linewidth=1.0, alpha=0.5,
    )
    fig.add_artist(line)


def _blurb(fig, text: str, y: float = 0.04):
    """Add a descriptive blurb at the bottom of a page."""
    fig.text(
        0.5, y, text,
        fontsize=8.5, color="#495057",
        ha="center", va="bottom",
        wrap=True,
        transform=fig.transFigure,
        style="italic",
    )


def utc_to_edt_label(hour_utc: int) -> str:
    """Return 'HH EDT' label for a UTC hour (UTC-4 for March EDT)."""
    h = (hour_utc + EDT_OFFSET) % 24
    suffix = "EDT"
    return f"{h:02d}:00 {suffix}"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection(database_url: str):
    return psycopg2.connect(database_url)


def query_df(conn, sql: str, params=None) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_summary(conn, day_start, day_end) -> dict:
    sql = """
        SELECT
            COUNT(*) AS total_reports,
            COUNT(DISTINCT pr.hex) AS unique_aircraft,
            COUNT(DISTINCT pr.session_id) AS sessions_in_window
        FROM position_reports pr
        WHERE pr.report_time >= %s AND pr.report_time < %s
    """
    row = query_df(conn, sql, (day_start, day_end)).iloc[0]
    return row.to_dict()


def load_sessions(conn, day_start, day_end) -> pd.DataFrame:
    sql = """
        SELECT
            session_id, hex, callsign, started_at, ended_at,
            on_ground, departure_airport_icao, arrival_airport_icao,
            total_distance_nm, trajectory_geom IS NOT NULL AS has_trajectory,
            created_at
        FROM flight_sessions
        WHERE started_at >= %s AND started_at < %s
    """
    return query_df(conn, sql, (day_start, day_end))


def load_hourly(conn, day_start, day_end) -> pd.DataFrame:
    sql = """
        SELECT
            date_trunc('hour', report_time) AS hour,
            COUNT(*) AS reports,
            COUNT(DISTINCT hex) AS unique_aircraft
        FROM position_reports
        WHERE report_time >= %s AND report_time < %s
        GROUP BY 1
        ORDER BY 1
    """
    return query_df(conn, sql, (day_start, day_end))


def load_per_minute(conn, day_start, day_end) -> pd.DataFrame:
    sql = """
        SELECT
            date_trunc('minute', report_time) AS minute,
            COUNT(*) AS reports
        FROM position_reports
        WHERE report_time >= %s AND report_time < %s
        GROUP BY 1
        ORDER BY 1
    """
    return query_df(conn, sql, (day_start, day_end))


def load_positions(conn, day_start, day_end) -> pd.DataFrame:
    sql = """
        SELECT
            report_time, hex, lat, lon,
            alt_ft, speed_kts, vrate_fpm, track,
            flight_phase, squawk, on_ground, category,
            session_id
        FROM position_reports
        WHERE report_time >= %s AND report_time < %s
    """
    return query_df(conn, sql, (day_start, day_end))


def load_concurrent_sessions(conn, day_start, day_end) -> pd.DataFrame:
    sql = """
        WITH hours AS (
            SELECT generate_series(%s::timestamptz, %s::timestamptz - interval '1 hour', interval '1 hour') AS hour_start
        )
        SELECT
            h.hour_start,
            COUNT(s.session_id) AS concurrent_sessions
        FROM hours h
        LEFT JOIN flight_sessions s
            ON s.started_at < (h.hour_start + interval '1 hour')
            AND (s.ended_at IS NULL OR s.ended_at >= h.hour_start)
        GROUP BY 1
        ORDER BY 1
    """
    return query_df(conn, sql, (day_start, day_end))


def load_airports(conn) -> pd.DataFrame:
    try:
        return query_df(conn, "SELECT icao_code, lat, lon FROM airports")
    except Exception:
        conn.rollback()
        return pd.DataFrame(columns=["icao_code", "lat", "lon"])


def load_null_rates(conn, day_start, day_end) -> pd.DataFrame:
    sql = """
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN alt_ft IS NULL THEN 1 ELSE 0 END) AS null_alt_ft,
            SUM(CASE WHEN speed_kts IS NULL THEN 1 ELSE 0 END) AS null_speed_kts,
            SUM(CASE WHEN vrate_fpm IS NULL THEN 1 ELSE 0 END) AS null_vrate_fpm,
            SUM(CASE WHEN track IS NULL THEN 1 ELSE 0 END) AS null_track,
            SUM(CASE WHEN squawk IS NULL THEN 1 ELSE 0 END) AS null_squawk,
            SUM(CASE WHEN category IS NULL THEN 1 ELSE 0 END) AS null_category
        FROM position_reports
        WHERE report_time >= %s AND report_time < %s
    """
    return query_df(conn, sql, (day_start, day_end))


def load_partition_sizes(conn, day_start, day_end) -> pd.DataFrame:
    report_date = day_start.date() if hasattr(day_start, "date") else day_start
    sql = """
        SELECT
            child.relname AS partition_name,
            pg_size_pretty(pg_total_relation_size(child.oid)) AS total_size,
            pg_total_relation_size(child.oid) AS size_bytes
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        WHERE parent.relname = 'position_reports'
          AND child.relname LIKE %s
        ORDER BY child.relname
    """
    date_str = report_date.strftime("%Y_%m")
    return query_df(conn, sql, (f"%{date_str}%",))


def load_db_size(conn) -> str:
    sql = "SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size"
    return query_df(conn, sql).iloc[0]["db_size"]


def load_registry(conn) -> pd.DataFrame:
    """Load aircraft_registry for JOIN enrichment. Returns empty DF if table missing/empty."""
    try:
        df = query_df(conn, "SELECT hex, n_number, manufacturer, model, aircraft_type, fleet_category FROM aircraft_registry")
        return df
    except Exception:
        conn.rollback()
        return pd.DataFrame(columns=["hex", "n_number", "manufacturer", "model", "aircraft_type", "fleet_category"])


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def detect_gaps(hourly_df: pd.DataFrame, day_start, threshold_minutes: int = 15):
    """Return list of dicts with gap start, end, duration."""
    if hourly_df.empty:
        return []
    gaps = []
    hours_with_data = set(hourly_df["hour"].dt.floor("h").tolist())
    current_gap_start = None
    for h in range(24):
        hour_ts = day_start + timedelta(hours=h)
        if hour_ts not in hours_with_data:
            if current_gap_start is None:
                current_gap_start = hour_ts
        else:
            if current_gap_start is not None:
                gap_end = hour_ts
                duration = (gap_end - current_gap_start).total_seconds() / 60
                if duration >= threshold_minutes:
                    gaps.append({
                        "start": current_gap_start,
                        "end": gap_end,
                        "duration_min": int(duration),
                    })
                current_gap_start = None
    if current_gap_start is not None:
        gap_end = day_start + timedelta(hours=24)
        duration = (gap_end - current_gap_start).total_seconds() / 60
        if duration >= threshold_minutes:
            gaps.append({
                "start": current_gap_start,
                "end": gap_end,
                "duration_min": int(duration),
            })
    return gaps


def extract_callsign_prefix(callsign) -> str:
    if not callsign or str(callsign).strip() == "":
        return "Unknown"
    cs = str(callsign).strip().upper()
    if cs.startswith("N") and len(cs) > 1 and cs[1:2].isdigit():
        return "GA (N-reg)"
    prefix = ""
    for c in cs:
        if c.isalpha():
            prefix += c
        else:
            break
    return prefix if prefix else "Unknown"


def classify_flight(callsign, squawk=None) -> str:
    if not callsign or str(callsign).strip() == "":
        return "Unknown"
    cs = str(callsign).strip().upper()
    prefix = extract_callsign_prefix(cs)
    if prefix in AIRLINE_PREFIXES:
        return "Commercial"
    if cs.startswith("N") and len(cs) > 1 and cs[1:2].isdigit():
        return "GA"
    if prefix in MILITARY_PREFIXES:
        return "Military"
    if squawk is not None:
        try:
            sq = int(str(squawk), 8)
            if 0o0100 <= sq <= 0o0177:
                return "Military"
        except (ValueError, TypeError):
            pass
    return "Unknown"


def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    R = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def theoretical_range_nm(alt_ft: np.ndarray, station_alt_ft: float = 900.0) -> np.ndarray:
    return 1.23 * (np.sqrt(np.maximum(alt_ft, 0)) + math.sqrt(station_alt_ft))


# ---------------------------------------------------------------------------
# Output path
# ---------------------------------------------------------------------------

def output_path(output_dir: str, report_date: date) -> Path:
    return (
        Path(output_dir)
        / report_date.strftime("%Y")
        / report_date.strftime("%m")
        / f"planegraph-daily-{report_date.strftime('%Y-%m-%d')}.pdf"
    )


# ---------------------------------------------------------------------------
# Page generators
# ---------------------------------------------------------------------------

def page1_executive_summary(pdf, report_date, summary, hourly_df, sessions_df, gaps, day_start, day_end, ts):
    """Page 1: Cover / Executive Summary."""
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Executive Summary", 1)

    has_data_hours = len(hourly_df)
    completeness_pct = has_data_hours / 24 * 100
    is_partial = has_data_hours < 24

    data_min_time = hourly_df["hour"].min() if not hourly_df.empty else day_start
    data_max_time = (hourly_df["hour"].max() + timedelta(hours=1)) if not hourly_df.empty else day_end
    actual_hours = (data_max_time - data_min_time).total_seconds() / 3600

    total_reports = int(summary.get("total_reports", 0))
    unique_aircraft = int(summary.get("unique_aircraft", 0))
    total_sessions = len(sessions_df)

    traj_sessions = int(sessions_df["has_trajectory"].sum()) if not sessions_df.empty else 0
    traj_pct = traj_sessions / total_sessions * 100 if total_sessions > 0 else 0

    # --- Partial day warning banner ---
    y_cursor = 0.92
    if is_partial:
        gap_list = ", ".join(
            f"{g['start'].strftime('%H:%M')}–{g['end'].strftime('%H:%M')}"
            for g in gaps
        ) or "none detected"
        fig.text(
            0.5, y_cursor,
            f"⚠ PARTIAL REPORT — {actual_hours:.1f}h of 24h  |  Gaps: {gap_list}",
            fontsize=10, fontweight="bold", color="#856404",
            ha="center", va="top",
            transform=fig.transFigure,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff3cd", edgecolor="#ffc107", alpha=0.95),
        )
        y_cursor -= 0.08

    # --- Big-number metric cards ---
    cards = [
        ("Total Reports", f"{total_reports:,}"),
        ("Unique Aircraft", f"{unique_aircraft:,}"),
        ("Flight Sessions", f"{total_sessions:,}"),
        ("Traj. Completeness", f"{traj_pct:.1f}%"),
    ]
    card_w = 0.20
    card_h = 0.10
    card_y = y_cursor - card_h - 0.01
    for i, (label, value) in enumerate(cards):
        x = 0.05 + i * (card_w + 0.02)
        rect = plt.Rectangle(
            (x, card_y), card_w, card_h,
            transform=fig.transFigure, figure=fig,
            facecolor=PANEL_BG, edgecolor=GRID_COLOR, linewidth=1.2,
        )
        fig.add_artist(rect)
        fig.text(x + card_w / 2, card_y + card_h * 0.65, value,
                 fontsize=18, fontweight="bold", color=ACCENT,
                 ha="center", va="center", transform=fig.transFigure)
        fig.text(x + card_w / 2, card_y + card_h * 0.2, label,
                 fontsize=8, color=TEXT_COLOR,
                 ha="center", va="center", transform=fig.transFigure)

    y_cursor = card_y - 0.02

    # --- Mini hourly bar chart ---
    ax_mini = fig.add_axes([0.05, y_cursor - 0.10, 0.88, 0.09])
    ax_mini.set_facecolor(PANEL_BG)
    hours = np.arange(24)
    reports_by_hour = np.zeros(24)
    if not hourly_df.empty:
        for _, row in hourly_df.iterrows():
            reports_by_hour[row["hour"].hour] = row["reports"]
    gap_hours = set()
    for g in gaps:
        for h in range(g["start"].hour, g["end"].hour if g["end"].hour > g["start"].hour else 24):
            gap_hours.add(h)
    bar_colors = ["#adb5bd" if h in gap_hours else BLUE for h in hours]
    ax_mini.bar(hours, reports_by_hour, color=bar_colors, width=0.85)
    ax_mini.set_xlim(-0.5, 23.5)
    ax_mini.set_xticks(hours[::2])
    ax_mini.set_xticklabels([f"{h:02d}" for h in hours[::2]], fontsize=6)
    ax_mini.set_yticks([])
    ax_mini.set_xlabel("Hour UTC", fontsize=7)
    ax_mini.set_title("Reports per Hour (gaps shaded)", fontsize=8, pad=2)
    for spine in ax_mini.spines.values():
        spine.set_edgecolor(GRID_COLOR)
    y_cursor -= 0.13

    # --- Secondary stats table ---
    if not sessions_df.empty:
        closed = sessions_df.dropna(subset=["ended_at"])
        if not closed.empty:
            durations = (closed["ended_at"] - closed["started_at"]).dt.total_seconds() / 60
            avg_dur = f"{durations.mean():.1f} min"
            med_dur = f"{durations.median():.1f} min"
        else:
            avg_dur = med_dur = "N/A"
    else:
        avg_dur = med_dur = "N/A"

    if not hourly_df.empty:
        peak_row = hourly_df.loc[hourly_df["reports"].idxmax()]
        peak_h = peak_row["hour"].hour
        peak_hour_str = f"{peak_h:02d}:00 UTC / {utc_to_edt_label(peak_h)}"
    else:
        peak_hour_str = "N/A"

    stats = [
        ("Peak hour (reports)", peak_hour_str),
        ("Avg session duration", avg_dur),
        ("Median session duration", med_dur),
        ("Data completeness", f"{has_data_hours}/24 hrs ({completeness_pct:.1f}%)"),
        ("Report generated", ts.strftime("%Y-%m-%d %H:%M:%S UTC")),
    ]

    ax_stats = fig.add_axes([0.05, y_cursor - 0.22, 0.55, 0.20])
    ax_stats.set_axis_off()
    ax_stats.set_facecolor(LIGHT_BG)
    rh = 1.0 / len(stats)
    for i, (label, value) in enumerate(stats):
        y = 1.0 - i * rh
        bg = PANEL_BG if i % 2 == 0 else LIGHT_BG
        ax_stats.axhspan(y - rh, y, color=bg, zorder=0)
        ax_stats.text(0.01, y - rh / 2, label, va="center", color=TEXT_COLOR, fontsize=8.5)
        ax_stats.text(0.62, y - rh / 2, value, va="center", color=ACCENT, fontsize=8.5, fontweight="bold")
    ax_stats.set_xlim(0, 1)
    ax_stats.set_ylim(0, 1)

    # --- Phase distribution strip (bottom) ---
    ax_phase = fig.add_axes([0.05, 0.03, 0.88, 0.06])
    ax_phase.set_facecolor(PANEL_BG)
    ax_phase.set_title("Flight Phase Distribution", fontsize=8, pad=2)

    _blurb(fig, "Summary metrics for the 24-hour UTC reporting window. Grey bars in hourly chart indicate data gaps.", y=0.005)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 1 done")


def page2_temporal_profile(pdf, report_date, hourly_df, gaps, day_start):
    """Page 2: Reports per hour (bar) + unique aircraft per hour (line), EDT secondary axis."""
    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Temporal Traffic Profile", 2)
    fig.subplots_adjust(top=0.90, bottom=0.12, left=0.08, right=0.97)

    hours = np.arange(24)
    reports_by_hour = np.zeros(24)
    unique_by_hour = np.zeros(24)
    if not hourly_df.empty:
        for _, row in hourly_df.iterrows():
            h = row["hour"].hour
            reports_by_hour[h] = row["reports"]
            unique_by_hour[h] = row["unique_aircraft"]

    # Bar chart: reports per hour
    max_r = max(reports_by_hour.max(), 1)
    bar_colors = [plt.cm.Blues(0.4 + 0.6 * v / max_r) for v in reports_by_hour]
    ax.bar(hours, reports_by_hour, color=bar_colors, width=0.85, label="Reports/hr", zorder=3)
    ax.set_ylabel("Position Reports / Hour", color=TEXT_COLOR)
    ax.set_xlabel("Hour (UTC)", color=TEXT_COLOR)

    # Overlay line: unique aircraft
    ax2 = ax.twinx()
    ax2.plot(hours, unique_by_hour, color=ACCENT, marker="o", markersize=5,
             linewidth=2, label="Unique aircraft", zorder=4)
    ax2.set_ylabel("Unique Aircraft / Hour", color=ACCENT)
    ax2.tick_params(axis="y", colors=ACCENT)
    ax2.spines["right"].set_edgecolor(ACCENT)

    # Gap shading
    for gap in gaps:
        g_start = gap["start"].hour - 0.5
        g_end = (gap["end"].hour if gap["end"].hour > gap["start"].hour else 24) - 0.5
        ax.axvspan(g_start, g_end, alpha=0.18, color="#dc3545", zorder=2, label="_gap")
        ax.annotate(
            f"Gap\n{gap['duration_min']}m",
            xy=((gap["start"].hour + (gap["end"].hour if gap["end"].hour > gap["start"].hour else 24)) / 2 - 0.5, max_r * 0.6),
            fontsize=7, color=ACCENT, ha="center",
        )

    # X-axis: UTC labels + EDT secondary labels
    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(hours)
    ax.set_xticklabels([f"{h:02d}:00" for h in hours], rotation=45, ha="right", fontsize=7)

    # EDT secondary x-axis via text annotations
    for h in hours[::2]:
        ax.text(h, -max_r * 0.09,
                f"{utc_to_edt_label(h).split()[0]}",
                fontsize=6, ha="center", color="#6c757d",
                transform=ax.get_xaxis_transform())

    ax.grid(axis="y", alpha=0.5)
    ax.set_title("Hourly Traffic Profile", fontsize=12)

    # Legend
    lines = [
        matplotlib.patches.Patch(facecolor=BLUE, label="Reports/hr"),
        matplotlib.lines.Line2D([0], [0], color=ACCENT, marker="o", markersize=5, label="Unique aircraft"),
    ]
    ax.legend(handles=lines, loc="upper left", fontsize=8)

    # Find peak
    if reports_by_hour.max() > 0:
        peak_h = int(reports_by_hour.argmax())
        _blurb(fig,
               f"Peak traffic at {peak_h:02d}:00 UTC / {utc_to_edt_label(peak_h)}. "
               f"Grey-shaded bands indicate data gaps. "
               f"The red line shows unique aircraft per hour, a proxy for traffic diversity.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 2 done")


def page3_concurrent_sessions(pdf, report_date, concurrent_df, gaps):
    """Page 3: Area chart of concurrent active sessions per hour."""
    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Concurrent Sessions", 3)
    fig.subplots_adjust(top=0.90, bottom=0.12, left=0.09, right=0.97)

    hours = np.arange(24)
    concurrent_by_hour = np.zeros(24)
    if not concurrent_df.empty:
        for _, row in concurrent_df.iterrows():
            h = row["hour_start"].hour
            concurrent_by_hour[h] = row["concurrent_sessions"]

    ax.fill_between(hours, concurrent_by_hour, alpha=0.3, color=BLUE)
    ax.plot(hours, concurrent_by_hour, color=BLUE, linewidth=2.5, marker="o", markersize=4, zorder=3)

    for gap in gaps:
        g_start = gap["start"].hour - 0.5
        g_end = (gap["end"].hour if gap["end"].hour > gap["start"].hour else 24) - 0.5
        ax.axvspan(g_start, g_end, alpha=0.15, color=ACCENT, zorder=2)

    peak_c = concurrent_by_hour.max()
    if peak_c > 0:
        ax.axhline(peak_c, color=ACCENT, linewidth=1, linestyle="--", alpha=0.6, label=f"Peak: {peak_c:.0f}")
        ax.legend(fontsize=8)

    ax.set_xlim(-0.5, 23.5)
    ax.set_xticks(hours[::2])
    ax.set_xticklabels([f"{h:02d}:00" for h in hours[::2]], rotation=45, ha="right", fontsize=8)
    ax.set_xlabel("Hour (UTC)")
    ax.set_ylabel("Concurrent Active Sessions")
    ax.set_title("Concurrent Active Sessions per Hour", fontsize=12)
    ax.grid(axis="y", alpha=0.5)

    shape = "a sustained plateau" if (concurrent_by_hour > 0).sum() > 18 else "sharp peaks"
    _blurb(fig,
           f"Concurrent active sessions show {shape}. "
           f"Peak concurrency reached {peak_c:.0f} sessions. "
           f"A flat plateau indicates sustained enroute traffic; sharp peaks suggest wave-based scheduling.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 3 done")


def page4_spatial(pdf, report_date, positions_df, airports_df, station_lat=None, station_lon=None):
    """Page 4: Reception footprint hexbin on OSM basemap."""
    try:
        import contextily as cx
        import geopandas as gpd
        cx.set_cache_dir("/opt/planegraph/cache/tiles")
        has_cx = True
    except Exception:
        has_cx = False

    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Reception Footprint (Map)", 4)
    fig.subplots_adjust(top=0.90, bottom=0.10, left=0.06, right=0.97)

    pos_valid = positions_df.dropna(subset=["lat", "lon"])
    lon_min, lon_max, lat_min, lat_max = MAP_EXTENT

    if not pos_valid.empty and has_cx:
        try:
            gdf = gpd.GeoDataFrame(
                pos_valid,
                geometry=gpd.points_from_xy(pos_valid["lon"], pos_valid["lat"]),
                crs="EPSG:4326",
            ).to_crs("EPSG:3857")

            hb = ax.hexbin(
                gdf.geometry.x, gdf.geometry.y,
                gridsize=80, cmap="YlOrRd", mincnt=1, alpha=0.7, zorder=3,
            )
            plt.colorbar(hb, ax=ax, label="Reports", shrink=0.8)

            # Set extent in Web Mercator
            import pyproj
            transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
            xmin, ymin = transformer.transform(lon_min, lat_min)
            xmax, ymax = transformer.transform(lon_max, lat_max)
            ax.set_xlim(xmin, xmax)
            ax.set_ylim(ymin, ymax)

            cx.add_basemap(ax, source=cx.providers.OpenStreetMap.Mapnik, zoom=9)
            ax.set_axis_off()

            # Airport markers
            combined_airports = list(COLUMBUS_AIRPORTS)
            if not airports_df.empty:
                for _, ap in airports_df.iterrows():
                    combined_airports.append({"icao_code": ap["icao_code"], "lat": ap["lat"], "lon": ap["lon"]})

            for ap in combined_airports:
                ax_pt, ay_pt = transformer.transform(ap["lon"], ap["lat"])
                ax.plot(ax_pt, ay_pt, "^", color=BLUE, markersize=10, zorder=6)
                ax.annotate(
                    ap["icao_code"], (ax_pt, ay_pt),
                    xytext=(5, 5), textcoords="offset points",
                    fontsize=8, fontweight="bold", color=BLUE,
                    zorder=7,
                )

            # Station marker + range rings
            if station_lat is not None and station_lon is not None:
                sx, sy = transformer.transform(station_lon, station_lat)
                ax.plot(sx, sy, "r*", markersize=16, zorder=8, label="Station")
                for nm in [25, 50, 75]:
                    km = nm * 1.852 * 1000  # to meters
                    circle = plt.Circle((sx, sy), km, fill=False, edgecolor=ACCENT,
                                       linewidth=1.0, linestyle="--", alpha=0.6, zorder=5)
                    ax.add_patch(circle)
                    ax.text(sx, sy + km, f"{nm} NM", fontsize=7, color=ACCENT,
                            ha="center", va="bottom", zorder=7)

            ax.set_title("Reception Footprint — OSM Basemap", fontsize=12, pad=8)

        except Exception as exc:
            _fallback_hexbin(ax, pos_valid, airports_df, station_lat, station_lon, report_date)
            fig.text(0.5, 0.06, f"Note: basemap unavailable ({exc})", ha="center", fontsize=7, color="#6c757d")
    else:
        _fallback_hexbin(ax, pos_valid, airports_df, station_lat, station_lon, report_date)

    _blurb(fig,
           "Hexbin heatmap shows reception density. Red star = station. "
           "Dashed circles = 25/50/75 NM range rings. Triangles = local airports. "
           "Hot spots near KCMH/KLCK indicate terminal area concentrations.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 4 done")


def _fallback_hexbin(ax, pos_valid, airports_df, station_lat, station_lon, report_date):
    """Plain hexbin without basemap (fallback)."""
    lon_min, lon_max, lat_min, lat_max = MAP_EXTENT
    if not pos_valid.empty:
        hb = ax.hexbin(
            pos_valid["lon"], pos_valid["lat"],
            gridsize=80, cmap="YlOrRd", mincnt=1,
        )
        plt.colorbar(hb, ax=ax, label="Reports", shrink=0.8)
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Reception Footprint", fontsize=12)
    ax.grid(alpha=0.3)
    if station_lat is not None and station_lon is not None:
        ax.plot(station_lon, station_lat, "r*", markersize=14, zorder=6, label="Station")
    for ap in COLUMBUS_AIRPORTS:
        ax.plot(ap["lon"], ap["lat"], "^", color=BLUE, markersize=8, zorder=5)
        ax.annotate(ap["icao_code"], (ap["lon"], ap["lat"]),
                    xytext=(3, 3), textcoords="offset points", fontsize=7, color=BLUE)


def page5_track_rose(pdf, report_date, positions_df):
    """Page 5: Full-page polar histogram of track angles."""
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Track Rose (Directional Flow)", 5)

    ax = fig.add_subplot(1, 1, 1, projection="polar")
    ax.set_position([0.15, 0.12, 0.70, 0.72])
    ax.set_facecolor(PANEL_BG)

    track = positions_df["track"].dropna()
    if not track.empty:
        bins = np.linspace(0, 2 * math.pi, 37)
        track_rad = np.radians(track)
        counts, _ = np.histogram(track_rad, bins=bins)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        bar_width = 2 * math.pi / 36
        colors = plt.cm.hot(counts / max(counts.max(), 1))
        ax.bar(
            bin_centers, counts,
            width=bar_width, bottom=0,
            color=colors, alpha=0.85, edgecolor="white", linewidth=0.3,
        )

        # Compass labels
        compass = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
        for deg, label in compass.items():
            ax.text(
                math.radians(deg), ax.get_ylim()[1] * 1.12,
                label, ha="center", va="center",
                fontsize=10, fontweight="bold", color=TEXT_COLOR,
            )

        dominant_bin = bin_centers[counts.argmax()]
        dominant_deg = math.degrees(dominant_bin) % 360
    else:
        dominant_deg = 0

    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.tick_params(colors=TEXT_COLOR, labelsize=7)
    ax.set_title("Track Rose Diagram (36 × 10° bins)", fontsize=12, pad=20)

    _blurb(fig,
           f"Dominant flow direction ~{dominant_deg:.0f}°. "
           "Strong N/S alignment suggests IFR corridor traffic (e.g., J146/J80). "
           "E/W flows correlate with transcontinental routes. "
           "Symmetric lobes indicate bidirectional runway operations.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 5 done")


def page6_altitude(pdf, report_date, positions_df):
    """Page 6: Altitude histogram with annotations."""
    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Altitude Analysis", 6)
    fig.subplots_adjust(top=0.90, bottom=0.13, left=0.09, right=0.97)

    alt = positions_df["alt_ft"].dropna()
    null_count = positions_df["alt_ft"].isna().sum()
    alt_clipped = alt[(alt >= 0) & (alt <= 50000)]
    bins = np.arange(0, 51000, 1000)

    ax.hist(alt_clipped, bins=bins, color=BLUE, alpha=0.75, edgecolor="white", linewidth=0.2)

    if len(alt_clipped) > 0:
        med = float(alt_clipped.median())
        p95 = float(alt_clipped.quantile(0.95))
        ax.axvline(med, color=ACCENT, linewidth=2, linestyle="--",
                   label=f"Median: {med:,.0f} ft")
        ax.axvline(p95, color=HIGHLIGHT, linewidth=2, linestyle=":",
                   label=f"P95: {p95:,.0f} ft")
        # Annotate enroute band
        ax.axvspan(35000, 41000, alpha=0.08, color=GREEN, label="FL350-410 (enroute)")
        ax.axvspan(0, 10000, alpha=0.06, color=PURPLE, label="<10,000 ft (terminal)")
        ax.legend(fontsize=8)

    ax.set_xlabel("Altitude (ft)")
    ax.set_ylabel("Report Count")
    ax.set_title(f"Altitude Distribution  ({null_count:,} NULLs excluded)", fontsize=12)
    ax.set_xlim(0, 50000)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.grid(axis="y", alpha=0.5)
    ax.grid(axis="x", alpha=0.2)

    _blurb(fig,
           "FL350–410 cluster (green shading) represents enroute jets. "
           "Sub-10,000 ft traffic (purple shading) = terminal approach/departure activity near KCMH. "
           "Gaps in the distribution may reflect Class B/C airspace floor effects.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 6 done")


def page7_speed_vrate(pdf, report_date, positions_df):
    """Page 7: Speed histogram + vertical rate histogram (stacked)."""
    fig, (ax_spd, ax_vr) = plt.subplots(2, 1, figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Speed & Vertical Rate", 7)
    fig.subplots_adjust(top=0.90, bottom=0.09, left=0.09, right=0.97, hspace=0.45)

    # Speed
    spd = positions_df["speed_kts"].dropna()
    null_spd = positions_df["speed_kts"].isna().sum()
    spd_clipped = spd[(spd >= 0) & (spd <= 700)]
    bins_spd = np.arange(0, 725, 25)
    ax_spd.hist(spd_clipped, bins=bins_spd, color=BLUE, alpha=0.75, edgecolor="white", linewidth=0.2)
    if len(spd_clipped) > 0:
        med_spd = float(spd_clipped.median())
        ax_spd.axvline(med_spd, color=ACCENT, linewidth=2, linestyle="--",
                       label=f"Median: {med_spd:.0f} kts")
        # Speed band annotations
        for lo, hi, label, color in [
            (200, 280, "Turboprop", "#6f42c1"),
            (350, 450, "Narrowbody", "#0d6efd"),
            (450, 520, "Widebody", "#198754"),
        ]:
            ax_spd.axvspan(lo, hi, alpha=0.08, color=color, label=label)
        ax_spd.legend(fontsize=7)
    ax_spd.set_xlabel("Ground Speed (kts)")
    ax_spd.set_ylabel("Count")
    ax_spd.set_title(f"Ground Speed Distribution  ({null_spd:,} NULLs excluded)", fontsize=11)
    ax_spd.grid(axis="y", alpha=0.5)

    # Vertical rate
    vr = positions_df["vrate_fpm"].dropna()
    null_vr = positions_df["vrate_fpm"].isna().sum()
    vr_clipped = vr[vr.abs() <= 8000]
    bins_vr = np.arange(-8000, 8200, 200)
    ax_vr.hist(vr_clipped, bins=bins_vr, color=GREEN, alpha=0.75, edgecolor="white", linewidth=0.2)
    ax_vr.axvline(0, color=ACCENT, linewidth=1.5, linestyle="-", alpha=0.7)
    if len(vr_clipped) > 0:
        climbers = int((vr_clipped > 200).sum())
        descenders = int((vr_clipped < -200).sum())
        ratio = climbers / descenders if descenders > 0 else float("inf")
        ax_vr.text(0.97, 0.93,
                   f"Climb/Descent ratio: {ratio:.2f}",
                   transform=ax_vr.transAxes, ha="right", va="top",
                   fontsize=8, color=TEXT_COLOR,
                   bbox=dict(boxstyle="round", facecolor=LIGHT_BG, edgecolor=GRID_COLOR))
    ax_vr.set_xlabel("Vertical Rate (fpm)")
    ax_vr.set_ylabel("Count")
    ax_vr.set_title(f"Vertical Rate Distribution  ({null_vr:,} NULLs excluded)", fontsize=11)
    ax_vr.grid(axis="y", alpha=0.5)

    _blurb(fig,
           "Speed clusters: turboprop ~200–280 kts, narrowbody jets ~350–450 kts, widebody ~450–520 kts. "
           "Vertical rate: positive = climbing, negative = descending. "
           "Balanced climb/descent ratio near 1.0 is expected for a capture volume centered on an airport.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 7 done")


def page8_speed_altitude_scatter(pdf, report_date, positions_df):
    """Page 8: Hexbin scatter of speed vs altitude."""
    fig, ax = plt.subplots(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Speed vs Altitude", 8)
    fig.subplots_adjust(top=0.90, bottom=0.10, left=0.09, right=0.97)

    scatter_df = positions_df[["speed_kts", "alt_ft"]].dropna()
    null_count = len(positions_df) - len(scatter_df)

    if len(scatter_df) > 0:
        hb = ax.hexbin(
            scatter_df["speed_kts"], scatter_df["alt_ft"],
            gridsize=70, cmap="inferno", mincnt=1,
            extent=[0, 700, 0, 50000],
        )
        plt.colorbar(hb, ax=ax, label="Count")

        # Annotate characteristic clusters
        for x, y, label in [
            (230, 8000, "Terminal\nturboprop"),
            (400, 30000, "Climb\ncorridor"),
            (480, 38000, "Cruise\nband"),
            (280, 15000, "Descent\ndecel."),
        ]:
            ax.annotate(label, (x, y), fontsize=7.5, color="white",
                        ha="center", va="center",
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="#00000066", edgecolor="none"))

    ax.set_xlabel("Ground Speed (kts)")
    ax.set_ylabel("Altitude (ft)")
    ax.set_title(f"Speed vs Altitude Hexbin  ({null_count:,} NULLs excluded)", fontsize=12)
    ax.set_xlim(0, 700)
    ax.set_ylim(0, 50000)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.grid(alpha=0.2)

    _blurb(fig,
           "Hexbin density of speed vs altitude. Bright areas = high report density. "
           "The cruise band at FL350–410 / 460–500 kts is the dominant cluster for commercial jets. "
           "The lower-speed, lower-altitude mass represents terminal-area operations.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 8 done")


def page9_fleet_composition(pdf, report_date, positions_df, sessions_df, registry_df):
    """Page 9: Fleet composition — callsign prefixes, fleet category, aircraft types."""
    registry_available = not registry_df.empty

    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Fleet Composition", 9)
    fig.subplots_adjust(top=0.90, bottom=0.10, left=0.07, right=0.97, wspace=0.45, hspace=0.55)

    ax1 = fig.add_subplot(2, 2, 1)
    ax2 = fig.add_subplot(2, 2, 2)
    ax3 = fig.add_subplot(2, 2, (3, 4))

    # --- Top 15 callsign prefixes ---
    if not sessions_df.empty:
        pfx = sessions_df["callsign"].apply(extract_callsign_prefix)
        pfx_counts = pfx.value_counts().head(15)
        colors = [BLUE] * len(pfx_counts)
        ax1.barh(pfx_counts.index[::-1], pfx_counts.values[::-1], color=colors, alpha=0.8)
        for i, (val, idx) in enumerate(zip(pfx_counts.values[::-1], pfx_counts.index[::-1])):
            ax1.text(val + 0.5, i, str(val), va="center", fontsize=7, color=TEXT_COLOR)
    ax1.set_xlabel("Sessions")
    ax1.set_title("Top 15 Callsign Prefixes", fontsize=10)
    ax1.grid(axis="x", alpha=0.4)

    # --- Fleet category distribution ---
    if registry_available:
        # JOIN sessions with registry
        if not sessions_df.empty:
            merged = sessions_df[["hex"]].drop_duplicates().merge(
                registry_df[["hex", "fleet_category"]], on="hex", how="left"
            )
            merged["fleet_category"] = merged["fleet_category"].fillna("Unknown")
            cat_counts = merged["fleet_category"].value_counts()
        else:
            cat_counts = pd.Series(dtype=int)
        fallback_note = ""
    else:
        # Fallback: callsign-based
        if not sessions_df.empty:
            cats = sessions_df["callsign"].apply(lambda cs: classify_flight(cs))
            cat_counts = cats.value_counts()
        else:
            cat_counts = pd.Series(dtype=int)
        fallback_note = "\n(FAA registry enrichment not available — using callsign classification)"

    cat_colors = {
        "Commercial": BLUE, "GA": GREEN, "Military": ACCENT,
        "Cargo": HIGHLIGHT, "Unknown": "#adb5bd",
    }
    if not cat_counts.empty:
        colors_pie = [cat_colors.get(c, "#adb5bd") for c in cat_counts.index]
        wedges, texts, autotexts = ax2.pie(
            cat_counts.values,
            labels=cat_counts.index,
            colors=colors_pie,
            autopct="%1.1f%%",
            pctdistance=0.75,
            startangle=90,
        )
        for t in texts + autotexts:
            t.set_fontsize(8)
            t.set_color(TEXT_COLOR)
    ax2.set_title(f"Fleet Category{fallback_note}", fontsize=9)

    # --- Top 10 aircraft types ---
    if registry_available and not sessions_df.empty:
        hex_types = sessions_df[["hex"]].drop_duplicates().merge(
            registry_df[["hex", "aircraft_type"]], on="hex", how="left"
        )
        type_counts = hex_types["aircraft_type"].dropna().value_counts().head(10)
    else:
        type_counts = pd.Series(dtype=int)

    if not type_counts.empty:
        ax3.barh(type_counts.index[::-1], type_counts.values[::-1], color=PURPLE, alpha=0.8)
        ax3.set_xlabel("Unique Aircraft")
        ax3.grid(axis="x", alpha=0.4)
    else:
        ax3.text(0.5, 0.5, "No aircraft type data available\n(run faa_registry_refresh.py to populate)",
                 ha="center", va="center", color=TEXT_COLOR, fontsize=10, transform=ax3.transAxes)
    ax3.set_title("Top 10 Aircraft Types (FAA Registry)", fontsize=10)

    enr_note = "enriched from FAA registry" if registry_available else "callsign-based fallback"
    _blurb(fig,
           f"Fleet composition based on {enr_note}. "
           "Commercial/GA/Cargo breakdown reflects the mix of traffic captured by the station. "
           "GA activity is typically highest on VFR weekend afternoons.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 9 done")


def page10_session_quality(pdf, report_date, sessions_df, positions_df, registry_df):
    """Page 10: Session duration histogram + top 15 aircraft table with N-numbers."""
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Session Quality & Top Aircraft", 10)
    fig.subplots_adjust(top=0.90, bottom=0.05, left=0.08, right=0.97, hspace=0.5)

    ax_dur = fig.add_subplot(2, 3, (1, 2))
    ax_traj = fig.add_subplot(2, 3, 3)
    ax_table = fig.add_subplot(2, 1, 2)
    ax_table.set_axis_off()
    ax_traj.set_axis_off()

    # --- Session duration histogram ---
    if not sessions_df.empty:
        closed = sessions_df.dropna(subset=["ended_at"]).copy()
        if not closed.empty:
            durations = (closed["ended_at"] - closed["started_at"]).dt.total_seconds() / 60
            dur_clipped = durations[(durations >= 0) & (durations <= 60)]
            bins = np.arange(0, 65, 5)
            ax_dur.hist(dur_clipped, bins=bins, color=BLUE, alpha=0.75, edgecolor="white")
            if len(dur_clipped) > 0:
                med = float(dur_clipped.median())
                ax_dur.axvline(med, color=ACCENT, linewidth=2, linestyle="--",
                               label=f"Median: {med:.1f} min")
                ax_dur.legend(fontsize=8)
        else:
            ax_dur.text(0.5, 0.5, "No closed sessions", ha="center", va="center",
                        color=TEXT_COLOR, transform=ax_dur.transAxes)
    ax_dur.set_xlabel("Duration (min, capped at 60)")
    ax_dur.set_ylabel("Sessions")
    ax_dur.set_title("Session Duration Distribution", fontsize=10)
    ax_dur.grid(axis="y", alpha=0.5)

    # --- Trajectory completeness ---
    if not sessions_df.empty:
        closed2 = sessions_df.dropna(subset=["ended_at"])
        total_closed = len(closed2)
        with_traj = int(closed2["has_trajectory"].sum()) if not closed2.empty else 0
        pct = with_traj / total_closed * 100 if total_closed > 0 else 0
        ax_traj.text(0.5, 0.65, f"{with_traj}/{total_closed}",
                     ha="center", va="center", fontsize=20, fontweight="bold",
                     color=ACCENT, transform=ax_traj.transAxes)
        ax_traj.text(0.5, 0.42, "sessions have\ntrajectories",
                     ha="center", va="center", fontsize=9, color=TEXT_COLOR,
                     transform=ax_traj.transAxes)
        ax_traj.text(0.5, 0.22, f"({pct:.1f}%)",
                     ha="center", va="center", fontsize=14, color=HIGHLIGHT,
                     transform=ax_traj.transAxes)
    ax_traj.set_title("Trajectory Completeness", fontsize=10)

    # --- Top 15 aircraft table ---
    if not positions_df.empty:
        report_counts = positions_df.groupby("hex").agg(reports=("hex", "count")).reset_index()
        if not sessions_df.empty:
            hex_callsign = sessions_df.groupby("hex")["callsign"].first().reset_index()
            hex_callsign.columns = ["hex", "callsign_name"]
            hex_dur = sessions_df.copy()
            hex_dur["duration_min"] = (hex_dur["ended_at"] - hex_dur["started_at"]).dt.total_seconds() / 60
            hex_dur_agg = hex_dur.groupby("hex").agg(
                total_duration=("duration_min", "sum"),
                total_distance=("total_distance_nm", "sum"),
            ).reset_index()
            report_counts = report_counts.merge(hex_callsign, on="hex", how="left")
            report_counts = report_counts.merge(hex_dur_agg, on="hex", how="left")

        report_counts = report_counts.sort_values("reports", ascending=False).head(15).reset_index(drop=True)

        hex_phases = positions_df.groupby("hex")["flight_phase"].apply(
            lambda x: "/".join(sorted(x.dropna().unique()))
        ).reset_index()
        hex_phases.columns = ["hex", "phases"]
        report_counts = report_counts.merge(hex_phases, on="hex", how="left")

        # Join registry for N-number and type
        if not registry_df.empty:
            report_counts = report_counts.merge(
                registry_df[["hex", "n_number", "aircraft_type"]], on="hex", how="left"
            )
        else:
            report_counts["n_number"] = None
            report_counts["aircraft_type"] = None

        def _fmt(val, default="—"):
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return default
            return str(val)

        col_labels = ["#", "Hex", "N-Number", "Type", "Callsign", "Reports", "Dur(m)", "Dist(NM)", "Phases"]
        table_data = []
        for i, row in report_counts.iterrows():
            table_data.append([
                str(i + 1),
                _fmt(row.get("hex")),
                _fmt(row.get("n_number")),
                (_fmt(row.get("aircraft_type")) or "—")[:22],
                (_fmt(row.get("callsign_name")) or "—")[:9],
                f"{int(row.get('reports', 0)):,}",
                f"{row.get('total_duration', 0):.0f}" if pd.notna(row.get("total_duration")) else "—",
                f"{row.get('total_distance', 0):.0f}" if pd.notna(row.get("total_distance")) else "—",
                (_fmt(row.get("phases")) or "—")[:20],
            ])

        if table_data:
            tbl = ax_table.table(
                cellText=table_data,
                colLabels=col_labels,
                loc="center",
                cellLoc="center",
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(7)
            tbl.scale(1, 1.35)
            for j in range(len(col_labels)):
                tbl[0, j].set_facecolor(ACCENT)
                tbl[0, j].set_text_props(color="white", fontweight="bold")
            for row_i in range(1, len(table_data) + 1):
                for col_j in range(len(col_labels)):
                    tbl[row_i, col_j].set_facecolor(PANEL_BG if row_i % 2 == 0 else LIGHT_BG)
                    tbl[row_i, col_j].set_text_props(color=TEXT_COLOR)
    ax_table.set_title("Top 15 Aircraft by Report Count", pad=8, fontsize=10)

    _blurb(fig,
           "Short sessions (< 5 min) are typically transient overflights. "
           "Longer sessions (> 20 min) suggest local circuit traffic or slow-moving GA. "
           "N-Numbers and aircraft types sourced from FAA registry; '—' indicates unregistered or not yet enriched.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 10 done")


def page11_data_quality(pdf, report_date, per_min_df, null_df, gaps, day_start):
    """Page 11: Ingest rate time series + NULL rates."""
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "Data Quality", 11)
    fig.subplots_adjust(top=0.90, bottom=0.09, left=0.09, right=0.97, hspace=0.55)

    ax_ingest = fig.add_subplot(2, 1, 1)
    ax_null = fig.add_subplot(2, 1, 2)

    # --- Ingest rate ---
    if not per_min_df.empty:
        ax_ingest.plot(
            per_min_df["minute"], per_min_df["reports"],
            color=BLUE, linewidth=0.7, alpha=0.85,
        )
        ax_ingest.fill_between(per_min_df["minute"], per_min_df["reports"], alpha=0.15, color=BLUE)
        for gap in gaps:
            ax_ingest.axvspan(gap["start"], gap["end"], alpha=0.25, color=ACCENT, zorder=2)
            mid = gap["start"] + (gap["end"] - gap["start"]) / 2
            ax_ingest.annotate(
                f"Gap\n{gap['duration_min']}m",
                xy=(mid, 0),
                xytext=(0, 18), textcoords="offset points",
                ha="center", color=ACCENT, fontsize=7,
                arrowprops=dict(arrowstyle="->", color=ACCENT, lw=0.7),
            )
    ax_ingest.set_ylabel("Reports / min")
    ax_ingest.set_title("Ingest Rate (Reports per Minute) — Primary Ops Health Indicator", fontsize=10)
    ax_ingest.grid(alpha=0.4)
    ax_ingest.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    ax_ingest.tick_params(axis="x", rotation=45, labelsize=7)

    # --- NULL rates ---
    if not null_df.empty:
        row = null_df.iloc[0]
        total = int(row.get("total", 1)) or 1
        null_cols = {
            "alt_ft": int(row.get("null_alt_ft", 0)),
            "speed_kts": int(row.get("null_speed_kts", 0)),
            "vrate_fpm": int(row.get("null_vrate_fpm", 0)),
            "track": int(row.get("null_track", 0)),
            "squawk": int(row.get("null_squawk", 0)),
            "category": int(row.get("null_category", 0)),
        }
        null_pcts = {k: v / total * 100 for k, v in null_cols.items()}
        cols = list(null_pcts.keys())
        pcts = list(null_pcts.values())
        bar_colors = [ACCENT if p > 30 else GREEN for p in pcts]
        bars = ax_null.barh(cols, pcts, color=bar_colors, alpha=0.8)
        for bar, pct in zip(bars, pcts):
            ax_null.text(pct + 0.5, bar.get_y() + bar.get_height() / 2,
                         f"{pct:.1f}%", va="center", fontsize=8, color=TEXT_COLOR)
        ax_null.set_xlabel("% NULL")
        ax_null.set_xlim(0, 100)
        ax_null.set_title("NULL Rates by Column", fontsize=10)
        ax_null.grid(axis="x", alpha=0.4)
    else:
        ax_null.text(0.5, 0.5, "No null rate data", ha="center", va="center",
                     color=TEXT_COLOR, transform=ax_null.transAxes)

    _blurb(fig,
           "Ingest rate gaps (red shading) indicate receiver or pipeline outages. "
           "High squawk NULL rate is expected — transponders don't always broadcast mode-C squawk. "
           "High alt_ft NULL rate would indicate a reception issue worth investigating.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 11 done")


def page12_system_health(pdf, report_date, partition_df, db_size_str):
    """Page 12: System health — partition sizes, DB size, storage projection."""
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(LIGHT_BG)
    add_page_header(fig, report_date, "System Health", 12)
    fig.subplots_adjust(top=0.90, bottom=0.09, left=0.07, right=0.97)

    ax = fig.add_subplot(1, 1, 1)
    ax.set_axis_off()

    lines = [
        f"Database total size: {db_size_str}",
        "",
    ]
    if not partition_df.empty:
        lines.append(f"{'Partition':<55}  {'Size':>10}")
        lines.append("─" * 70)
        total_bytes = 0
        for _, row in partition_df.iterrows():
            lines.append(f"  {row['partition_name']:<53}  {row['total_size']:>10}")
            total_bytes += int(row["size_bytes"])
        lines.append("")
        # Storage projection: if we have at least 1 partition
        if total_bytes > 0 and not partition_df.empty:
            avg_per_month = total_bytes  # crude: this month's partitions
            per_year = avg_per_month * 12
            lines.append(f"Estimated annual storage (position_reports): ~{per_year / 1e9:.1f} GB")
    else:
        lines.append("No partition size data available for this month.")

    lines.extend([
        "",
        "Station Hardware Metrics:",
        "  (placeholder — future integration with node_exporter metrics)",
        "",
        "Note: Partition sizes reflect PostgreSQL table + index storage including TOAST.",
    ])

    ax.text(
        0.03, 0.93, "\n".join(lines),
        va="top", ha="left",
        color=TEXT_COLOR, fontsize=9,
        fontfamily="monospace",
        transform=ax.transAxes,
        bbox=dict(boxstyle="round,pad=0.8", facecolor=PANEL_BG, edgecolor=GRID_COLOR),
    )
    ax.set_title("System Health & Storage", fontsize=12, pad=8)

    _blurb(fig,
           "Storage growth projection assumes uniform monthly partitions. "
           "Actual growth will vary with traffic density and seasonal patterns. "
           "PostgreSQL autovacuum and partition pruning keep operational overhead low.")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 12 done")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Planegraph daily station report generator (v2)")
    parser.add_argument("--date", help="Report date YYYY-MM-DD (default: yesterday UTC)")
    parser.add_argument("--station-lat", type=float, default=None)
    parser.add_argument("--station-lon", type=float, default=None)
    parser.add_argument("--output-dir", default="/opt/planegraph/reports/daily")
    return parser.parse_args()


def main():
    args = parse_args()
    ts = datetime.now(timezone.utc)

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(3)

    if args.date:
        try:
            report_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"ERROR: Invalid date format '{args.date}'. Use YYYY-MM-DD.", file=sys.stderr)
            sys.exit(3)
    else:
        report_date = (ts - timedelta(days=1)).date()

    day_start = datetime(report_date.year, report_date.month, report_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    print(f"[{ts.strftime('%H:%M:%S')}] Planegraph Daily Report v2 — {report_date}")
    print(f"[{ts.strftime('%H:%M:%S')}] Data window: {day_start} — {day_end}")

    station_lat = args.station_lat
    station_lon = args.station_lon
    if station_lat is None:
        try:
            station_lat = float(os.environ.get("STATION_LAT", ""))
        except (ValueError, TypeError):
            pass
    if station_lon is None:
        try:
            station_lon = float(os.environ.get("STATION_LON", ""))
        except (ValueError, TypeError):
            pass
    if station_lat is None or station_lon is None:
        print(f"[{ts.strftime('%H:%M:%S')}] Station coordinates not set — range rings will be skipped.")
        station_lat = station_lon = None

    try:
        conn = get_connection(database_url)
    except Exception as exc:
        print(f"ERROR: Database connection failed: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        print(f"[{ts.strftime('%H:%M:%S')}] Loading data ...")
        summary = load_summary(conn, day_start, day_end)

        if int(summary.get("total_reports", 0)) == 0:
            print(f"No data found for {report_date}. Exiting with code 1.")
            sys.exit(1)

        sessions_df = load_sessions(conn, day_start, day_end)
        hourly_df = load_hourly(conn, day_start, day_end)
        per_min_df = load_per_minute(conn, day_start, day_end)
        concurrent_df = load_concurrent_sessions(conn, day_start, day_end)
        airports_df = load_airports(conn)
        null_df = load_null_rates(conn, day_start, day_end)
        partition_df = load_partition_sizes(conn, day_start, day_end)
        db_size_str = load_db_size(conn)
        registry_df = load_registry(conn)

        print(f"[{ts.strftime('%H:%M:%S')}] Loading position reports ...")
        positions_df = load_positions(conn, day_start, day_end)

        for df, cols in [
            (sessions_df, ["started_at", "ended_at", "created_at"]),
            (hourly_df, ["hour"]),
            (per_min_df, ["minute"]),
            (concurrent_df, ["hour_start"]),
            (positions_df, ["report_time"]),
        ]:
            for col in cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True)

        for col in ["lat", "lon", "alt_ft", "track", "speed_kts", "vrate_fpm"]:
            if col in positions_df.columns:
                positions_df[col] = pd.to_numeric(positions_df[col], errors="coerce")

        print(f"[{ts.strftime('%H:%M:%S')}] {len(positions_df):,} position reports loaded.")
        if not registry_df.empty:
            print(f"[{ts.strftime('%H:%M:%S')}] {len(registry_df):,} FAA registry records available.")
        else:
            print(f"[{ts.strftime('%H:%M:%S')}] FAA registry empty — fleet pages will use callsign fallback.")

        gaps = detect_gaps(hourly_df, day_start)
        if gaps:
            print(f"[{ts.strftime('%H:%M:%S')}] {len(gaps)} data gap(s) detected.")

        out_path = output_path(args.output_dir, report_date)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[{ts.strftime('%H:%M:%S')}] Writing report to {out_path}")

        apply_light_style()

        with PdfPages(str(out_path)) as pdf:
            page1_executive_summary(pdf, report_date, summary, hourly_df, sessions_df, gaps, day_start, day_end, ts)
            page2_temporal_profile(pdf, report_date, hourly_df, gaps, day_start)
            page3_concurrent_sessions(pdf, report_date, concurrent_df, gaps)
            page4_spatial(pdf, report_date, positions_df, airports_df, station_lat, station_lon)
            page5_track_rose(pdf, report_date, positions_df)
            page6_altitude(pdf, report_date, positions_df)
            page7_speed_vrate(pdf, report_date, positions_df)
            page8_speed_altitude_scatter(pdf, report_date, positions_df)
            page9_fleet_composition(pdf, report_date, positions_df, sessions_df, registry_df)
            page10_session_quality(pdf, report_date, sessions_df, positions_df, registry_df)
            page11_data_quality(pdf, report_date, per_min_df, null_df, gaps, day_start)
            page12_system_health(pdf, report_date, partition_df, db_size_str)

        size_kb = out_path.stat().st_size // 1024
        print(f"[{ts.strftime('%H:%M:%S')}] Report complete: {out_path} ({size_kb:,} KB)")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
