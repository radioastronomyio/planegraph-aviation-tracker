#!/usr/bin/env python3
"""
Planegraph Daily Station Report Generator

Generates an 8-page PDF summarizing the previous day's ADS-B data.

Usage:
    python tools/daily_report.py
    python tools/daily_report.py --date 2026-03-21
    python tools/daily_report.py --date 2026-03-21 --station-lat 39.96 --station-lon -82.99
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
import numpy as np
import pandas as pd
import psycopg2
from matplotlib.backends.backend_pdf import PdfPages

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DARK_BG = "#1a1a2e"
PANEL_BG = "#16213e"
ACCENT = "#e94560"
TEXT_COLOR = "#e0e0e0"
GRID_COLOR = "#2a2a4a"
HIGHLIGHT = "#f5a623"

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
    "CLB": "#2ecc71",
    "CRZ": "#3498db",
    "DES": "#e74c3c",
    "APP": "#e67e22",
    "GND": "#95a5a6",
    "TOF": "#9b59b6",
    "LDG": "#f39c12",
    "UNKNOWN": "#7f8c8d",
}


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def apply_dark_style():
    plt.rcParams.update({
        "figure.facecolor": DARK_BG,
        "axes.facecolor": PANEL_BG,
        "axes.edgecolor": GRID_COLOR,
        "axes.labelcolor": TEXT_COLOR,
        "axes.titlecolor": TEXT_COLOR,
        "xtick.color": TEXT_COLOR,
        "ytick.color": TEXT_COLOR,
        "text.color": TEXT_COLOR,
        "grid.color": GRID_COLOR,
        "grid.alpha": 0.5,
        "legend.facecolor": PANEL_BG,
        "legend.edgecolor": GRID_COLOR,
        "legend.labelcolor": TEXT_COLOR,
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
    })


def add_page_header(fig, report_date: date, title: str):
    """Add a consistent header banner to every page."""
    fig.text(
        0.01, 0.97,
        f"PLANEGRAPH  |  {title}  |  {report_date.strftime('%Y-%m-%d')} UTC",
        fontsize=11, fontweight="bold", color=ACCENT,
        va="top", ha="left",
        transform=fig.transFigure,
    )
    fig.text(
        0.99, 0.97,
        "Daily Station Report",
        fontsize=9, color=TEXT_COLOR,
        va="top", ha="right",
        transform=fig.transFigure,
    )
    # Thin separator line
    line = plt.Line2D(
        [0.01, 0.99], [0.955, 0.955],
        transform=fig.transFigure,
        color=ACCENT, linewidth=0.8, alpha=0.6,
    )
    fig.add_artist(line)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection(database_url: str):
    """Return a psycopg2 connection."""
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
    """Load raw position reports (columns needed for plots)."""
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
    """For each hour, count sessions active during that hour."""
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


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def detect_gaps(hourly_df: pd.DataFrame, day_start, threshold_minutes: int = 15):
    """Return list of dicts with gap start, end, duration."""
    if hourly_df.empty:
        return []
    gaps = []
    # Use hourly data to approximate — mark hours with 0 reports as missing
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
    # Extract alphabetic prefix
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
    R = 3440.065  # Earth radius in NM
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
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(DARK_BG)
    add_page_header(fig, report_date, "Executive Summary")

    # --- Partial day detection ---
    has_data_hours = len(hourly_df)
    completeness_pct = has_data_hours / 24 * 100

    data_min_time = hourly_df["hour"].min() if not hourly_df.empty else day_start
    data_max_time = (hourly_df["hour"].max() + timedelta(hours=1)) if not hourly_df.empty else day_end
    actual_hours = (data_max_time - data_min_time).total_seconds() / 3600

    is_partial = has_data_hours < 24

    y_top = 0.90
    if is_partial:
        fig.text(
            0.5, y_top,
            f"PARTIAL REPORT  —  Data available from "
            f"{data_min_time.strftime('%H:%M')} to {data_max_time.strftime('%H:%M')} UTC "
            f"({actual_hours:.1f} hours of 24)",
            fontsize=11, fontweight="bold", color=HIGHLIGHT,
            ha="center", va="top",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#3a1a00", edgecolor=HIGHLIGHT, alpha=0.9),
        )
        y_top -= 0.07

    # --- Key metrics table ---
    total_sessions = len(sessions_df)
    traj_sessions = int(sessions_df["has_trajectory"].sum()) if not sessions_df.empty else 0

    if not sessions_df.empty and "started_at" in sessions_df and "ended_at" in sessions_df:
        closed = sessions_df.dropna(subset=["ended_at"])
        if not closed.empty:
            durations = (closed["ended_at"] - closed["started_at"]).dt.total_seconds() / 60
            avg_dur = f"{durations.mean():.1f} min"
        else:
            avg_dur = "N/A"
    else:
        avg_dur = "N/A"

    if not hourly_df.empty:
        peak_row = hourly_df.loc[hourly_df["reports"].idxmax()]
        peak_hour = peak_row["hour"].strftime("%H:00 UTC")
    else:
        peak_hour = "N/A"

    metrics = [
        ("Total position reports", f"{int(summary.get('total_reports', 0)):,}"),
        ("Unique aircraft (distinct hex)", f"{int(summary.get('unique_aircraft', 0)):,}"),
        ("Flight sessions started", f"{total_sessions:,}"),
        ("Sessions with trajectories", f"{traj_sessions:,}"),
        ("Average session duration", avg_dur),
        ("Peak hour (by report volume)", peak_hour),
        ("Data completeness (hourly buckets)", f"{has_data_hours}/24 ({completeness_pct:.1f}%)"),
        ("Report generated (UTC)", ts.strftime("%Y-%m-%d %H:%M:%S")),
    ]

    ax_table = fig.add_axes([0.05, 0.42, 0.88, y_top - 0.45])
    ax_table.set_axis_off()
    ax_table.set_facecolor(DARK_BG)

    row_height = 0.11
    for i, (label, value) in enumerate(metrics):
        y = 1.0 - i * row_height
        bg_color = PANEL_BG if i % 2 == 0 else "#1e1e3a"
        ax_table.axhspan(y - row_height, y, color=bg_color, zorder=0)
        ax_table.text(0.02, y - row_height / 2, label, va="center", color=TEXT_COLOR, fontsize=10)
        ax_table.text(0.75, y - row_height / 2, value, va="center", color=ACCENT, fontsize=10, fontweight="bold")
    ax_table.set_xlim(0, 1)
    ax_table.set_ylim(0, 1)

    # --- Gap table ---
    ax_gaps = fig.add_axes([0.05, 0.05, 0.88, 0.35])
    ax_gaps.set_axis_off()
    ax_gaps.set_facecolor(DARK_BG)

    if gaps:
        ax_gaps.text(0.0, 0.97, f"Data Gaps (>{15} min):", va="top", color=HIGHLIGHT, fontsize=10, fontweight="bold")
        headers = ["Gap Start (UTC)", "Gap End (UTC)", "Duration"]
        col_x = [0.0, 0.35, 0.70]
        ax_gaps.text(col_x[0], 0.88, headers[0], va="top", color=TEXT_COLOR, fontsize=9, fontweight="bold")
        ax_gaps.text(col_x[1], 0.88, headers[1], va="top", color=TEXT_COLOR, fontsize=9, fontweight="bold")
        ax_gaps.text(col_x[2], 0.88, headers[2], va="top", color=TEXT_COLOR, fontsize=9, fontweight="bold")
        for j, gap in enumerate(gaps):
            y = 0.80 - j * 0.12
            ax_gaps.text(col_x[0], y, gap["start"].strftime("%H:%M"), va="top", color=TEXT_COLOR, fontsize=9)
            ax_gaps.text(col_x[1], y, gap["end"].strftime("%H:%M"), va="top", color=TEXT_COLOR, fontsize=9)
            ax_gaps.text(col_x[2], y, f"{gap['duration_min']} min", va="top", color=ACCENT, fontsize=9)
    else:
        ax_gaps.text(0.0, 0.97, "No data gaps detected (all 24 hourly buckets have data).", va="top", color="#2ecc71", fontsize=10)

    ax_gaps.set_xlim(0, 1)
    ax_gaps.set_ylim(0, 1)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 1 done")


def page2_temporal_profile(pdf, report_date, hourly_df, concurrent_df, gaps, day_start):
    fig, axes = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True)
    fig.patch.set_facecolor(DARK_BG)
    add_page_header(fig, report_date, "Temporal Traffic Profile")
    fig.subplots_adjust(top=0.93, bottom=0.07, hspace=0.35, left=0.08, right=0.97)

    hours = np.arange(24)
    hour_labels = [f"{h:02d}:00" for h in hours]

    # Build full 24-hour arrays
    reports_by_hour = np.zeros(24)
    unique_by_hour = np.zeros(24)
    if not hourly_df.empty:
        for _, row in hourly_df.iterrows():
            h = row["hour"].hour
            reports_by_hour[h] = row["reports"]
            unique_by_hour[h] = row["unique_aircraft"]

    concurrent_by_hour = np.zeros(24)
    if not concurrent_df.empty:
        for _, row in concurrent_df.iterrows():
            h = row["hour_start"].hour
            concurrent_by_hour[h] = row["concurrent_sessions"]

    # Color bars by intensity
    max_r = max(reports_by_hour.max(), 1)
    bar_colors = [plt.cm.plasma(v / max_r) for v in reports_by_hour]

    # Plot 1: reports per hour
    ax0 = axes[0]
    ax0.bar(hours, reports_by_hour, color=bar_colors, zorder=3)
    ax0.set_ylabel("Reports / hr")
    ax0.set_title("Reports per Hour")
    ax0.grid(axis="y", zorder=0)

    # Plot 2: unique aircraft per hour
    ax1 = axes[1]
    ax1.plot(hours, unique_by_hour, color=ACCENT, marker="o", markersize=4, linewidth=1.5, zorder=3)
    ax1.fill_between(hours, unique_by_hour, alpha=0.2, color=ACCENT)
    ax1.set_ylabel("Aircraft / hr")
    ax1.set_title("Unique Aircraft per Hour")
    ax1.grid(axis="y", zorder=0)

    # Plot 3: concurrent sessions
    ax2 = axes[2]
    ax2.fill_between(hours, concurrent_by_hour, alpha=0.4, color="#3498db")
    ax2.plot(hours, concurrent_by_hour, color="#3498db", linewidth=1.5, zorder=3)
    ax2.set_ylabel("Sessions")
    ax2.set_title("Concurrent Active Sessions per Hour")
    ax2.grid(axis="y", zorder=0)
    ax2.set_xticks(hours[::2])
    ax2.set_xticklabels(hour_labels[::2], rotation=45, ha="right", fontsize=7)

    # Shade gap hours
    for gap in gaps:
        for ax in axes:
            gap_start_h = gap["start"].hour
            gap_end_h = gap["end"].hour if gap["end"].hour > gap["start"].hour else 24
            ax.axvspan(gap_start_h - 0.5, gap_end_h - 0.5, alpha=0.25, color="#e74c3c", zorder=2)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 2 done")


def page3_altitude_speed(pdf, report_date, positions_df):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8.5))
    fig.patch.set_facecolor(DARK_BG)
    add_page_header(fig, report_date, "Altitude & Speed Analysis")
    fig.subplots_adjust(top=0.91, bottom=0.08, hspace=0.45, wspace=0.35, left=0.08, right=0.97)

    # --- Altitude histogram ---
    ax = axes[0, 0]
    alt = positions_df["alt_ft"].dropna()
    null_count = positions_df["alt_ft"].isna().sum()
    alt_clipped = alt[(alt >= 0) & (alt <= 50000)]
    bins = np.arange(0, 51000, 1000)
    ax.hist(alt_clipped, bins=bins, color="#3498db", alpha=0.8, edgecolor="none")
    if len(alt_clipped) > 0:
        med = alt_clipped.median()
        p95 = alt_clipped.quantile(0.95)
        ax.axvline(med, color=ACCENT, linewidth=1.5, linestyle="--", label=f"Median: {med:,.0f} ft")
        ax.axvline(p95, color=HIGHLIGHT, linewidth=1.5, linestyle=":", label=f"P95: {p95:,.0f} ft")
        ax.legend(fontsize=7)
    ax.set_xlabel("Altitude (ft)")
    ax.set_ylabel("Count")
    ax.set_title(f"Altitude Distribution\n({null_count:,} NULLs excluded)")
    ax.grid(axis="y", alpha=0.5)

    # --- Speed histogram ---
    ax = axes[0, 1]
    spd = positions_df["speed_kts"].dropna()
    null_count = positions_df["speed_kts"].isna().sum()
    spd_clipped = spd[(spd >= 0) & (spd <= 700)]
    bins = np.arange(0, 725, 25)
    ax.hist(spd_clipped, bins=bins, color="#2ecc71", alpha=0.8, edgecolor="none")
    if len(spd_clipped) > 0:
        med = spd_clipped.median()
        ax.axvline(med, color=ACCENT, linewidth=1.5, linestyle="--", label=f"Median: {med:.0f} kts")
        ax.legend(fontsize=7)
    ax.set_xlabel("Speed (kts)")
    ax.set_ylabel("Count")
    ax.set_title(f"Ground Speed Distribution\n({null_count:,} NULLs excluded)")
    ax.grid(axis="y", alpha=0.5)

    # --- Speed vs altitude scatter ---
    ax = axes[1, 0]
    scatter_df = positions_df[["speed_kts", "alt_ft", "flight_phase"]].dropna(subset=["speed_kts", "alt_ft"])
    null_count = len(positions_df) - len(scatter_df)
    if len(scatter_df) > 50000:
        hb = ax.hexbin(
            scatter_df["speed_kts"], scatter_df["alt_ft"],
            gridsize=60, cmap="plasma", mincnt=1,
        )
        fig.colorbar(hb, ax=ax, label="Count")
    elif len(scatter_df) > 0:
        phases = scatter_df["flight_phase"].fillna("UNKNOWN")
        for phase in phases.unique():
            mask = phases == phase
            color = PHASE_COLORS.get(phase, "#7f8c8d")
            ax.scatter(
                scatter_df.loc[mask, "speed_kts"],
                scatter_df.loc[mask, "alt_ft"],
                c=color, alpha=0.05, s=1, label=phase,
            )
        ax.legend(fontsize=6, markerscale=5)
    ax.set_xlabel("Speed (kts)")
    ax.set_ylabel("Altitude (ft)")
    ax.set_title(f"Speed vs Altitude\n({null_count:,} NULLs excluded)")
    ax.grid(alpha=0.3)

    # --- Vertical rate distribution ---
    ax = axes[1, 1]
    vr = positions_df["vrate_fpm"].dropna()
    null_count = positions_df["vrate_fpm"].isna().sum()
    vr_clipped = vr[vr.abs() <= 8000]
    bins = np.arange(-8000, 8200, 200)
    ax.hist(vr_clipped, bins=bins, color="#9b59b6", alpha=0.8, edgecolor="none")
    if len(vr_clipped) > 0:
        climbers = (vr_clipped > 200).sum()
        descenders = (vr_clipped < -200).sum()
        ratio = climbers / descenders if descenders > 0 else float("inf")
        ax.text(
            0.97, 0.95,
            f"Climb/Descent ratio: {ratio:.2f}",
            transform=ax.transAxes, ha="right", va="top",
            color=TEXT_COLOR, fontsize=8,
            bbox=dict(boxstyle="round", facecolor=PANEL_BG, edgecolor=GRID_COLOR),
        )
    ax.axvline(0, color=ACCENT, linewidth=1, linestyle="-")
    ax.set_xlabel("Vertical Rate (fpm)")
    ax.set_ylabel("Count")
    ax.set_title(f"Vertical Rate Distribution\n({null_count:,} NULLs excluded)")
    ax.grid(axis="y", alpha=0.5)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 3 done")


def page4_spatial(pdf, report_date, positions_df, airports_df, station_lat=None, station_lon=None):
    has_station = station_lat is not None and station_lon is not None
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(DARK_BG)
    add_page_header(fig, report_date, "Spatial Coverage")

    if has_station:
        ax_hex = fig.add_subplot(2, 2, (1, 2))
        ax_rose = fig.add_subplot(2, 2, 3, projection="polar")
        ax_range = fig.add_subplot(2, 2, 4)
    else:
        ax_hex = fig.add_subplot(1, 2, 1)
        ax_rose = fig.add_subplot(1, 2, 2, projection="polar")

    fig.subplots_adjust(top=0.91, bottom=0.08, hspace=0.4, wspace=0.35, left=0.07, right=0.97)

    # --- Hexbin reception footprint ---
    pos_valid = positions_df.dropna(subset=["lat", "lon"])
    if not pos_valid.empty:
        hb = ax_hex.hexbin(
            pos_valid["lon"], pos_valid["lat"],
            gridsize=80, cmap="inferno", mincnt=1,
        )
        plt.colorbar(hb, ax=ax_hex, label="Reports", shrink=0.8)
    ax_hex.set_xlabel("Longitude")
    ax_hex.set_ylabel("Latitude")
    ax_hex.set_title("Reception Footprint")
    ax_hex.grid(alpha=0.3)

    if has_station:
        ax_hex.plot(station_lon, station_lat, "r*", markersize=14, zorder=10, label="Station")
        ax_hex.legend(fontsize=8)

    if not airports_df.empty:
        for _, ap in airports_df.iterrows():
            ax_hex.plot(ap["lon"], ap["lat"], "^", color=HIGHLIGHT, markersize=8, zorder=9)
            ax_hex.annotate(ap["icao_code"], (ap["lon"], ap["lat"]), color=HIGHLIGHT, fontsize=7,
                            xytext=(3, 3), textcoords="offset points")

    # --- Track rose ---
    track = positions_df["track"].dropna()
    if not track.empty:
        bins = np.linspace(0, 2 * math.pi, 37)
        track_rad = np.radians(track)
        counts, _ = np.histogram(track_rad, bins=bins)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        bar_width = 2 * math.pi / 36
        ax_rose.bar(
            bin_centers, counts,
            width=bar_width, bottom=0,
            color=plt.cm.plasma(counts / max(counts.max(), 1)),
            alpha=0.85, edgecolor="none",
        )
    ax_rose.set_theta_zero_location("N")
    ax_rose.set_theta_direction(-1)
    ax_rose.set_title("Track Rose Diagram", pad=15)
    ax_rose.tick_params(colors=TEXT_COLOR)
    ax_rose.set_facecolor(PANEL_BG)

    # --- Range vs altitude ---
    if has_station:
        pos_rng = positions_df.dropna(subset=["lat", "lon", "alt_ft"]).copy()
        if not pos_rng.empty:
            pos_rng["range_nm"] = pos_rng.apply(
                lambda r: haversine_nm(station_lat, station_lon, r["lat"], r["lon"]),
                axis=1,
            )
            sample = pos_rng.sample(min(30000, len(pos_rng)), random_state=42)
            ax_range.scatter(
                sample["alt_ft"], sample["range_nm"],
                alpha=0.05, s=1, color="#3498db",
            )
            alt_theory = np.linspace(0, 45000, 200)
            range_theory = theoretical_range_nm(alt_theory)
            ax_range.plot(alt_theory, range_theory, color=ACCENT, linewidth=1.5, linestyle="--",
                          label="Theoretical LoS")
            ax_range.legend(fontsize=8)
        ax_range.set_xlabel("Altitude (ft)")
        ax_range.set_ylabel("Range (NM)")
        ax_range.set_title("Reception Range vs Altitude")
        ax_range.grid(alpha=0.3)
    elif not has_station:
        fig.text(
            0.5, 0.12,
            "Station coordinates not provided — range plot skipped.",
            ha="center", color=TEXT_COLOR, fontsize=9, style="italic",
        )

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 4 done")


def page5_flight_phase(pdf, report_date, positions_df, hourly_df):
    fig, axes = plt.subplots(1, 2, figsize=(11, 8.5))
    fig.patch.set_facecolor(DARK_BG)
    add_page_header(fig, report_date, "Flight Phase Analysis")
    fig.subplots_adjust(top=0.91, bottom=0.1, left=0.1, right=0.97, wspace=0.4)

    phase_counts = positions_df["flight_phase"].fillna("UNKNOWN").value_counts()

    # --- Horizontal bar chart ---
    ax = axes[0]
    phases = phase_counts.index.tolist()
    counts = phase_counts.values
    colors = [PHASE_COLORS.get(p, "#7f8c8d") for p in phases]
    bars = ax.barh(phases, counts, color=colors, alpha=0.85)
    total = counts.sum()
    for bar, count in zip(bars, counts):
        pct = count / total * 100 if total > 0 else 0
        ax.text(
            bar.get_width() + total * 0.005, bar.get_y() + bar.get_height() / 2,
            f"{pct:.1f}%", va="center", color=TEXT_COLOR, fontsize=8,
        )
    ax.set_xlabel("Report Count")
    ax.set_title("Phase Distribution")
    ax.grid(axis="x", alpha=0.5)

    # Note if ground phases are absent
    ground_phases = {"GND", "TOF", "LDG"}
    missing = ground_phases - set(phases)
    if missing:
        ax.text(
            0.5, -0.12,
            f"Note: {', '.join(sorted(missing))} phases absent\n(expected with ADS-B line-of-sight limitations)",
            transform=ax.transAxes, ha="center", color=TEXT_COLOR, fontsize=7, style="italic",
        )

    # --- Phase by hour stacked area ---
    ax2 = axes[1]
    if not positions_df.empty and not hourly_df.empty:
        # Build phase proportions per hour
        pos_with_hour = positions_df.copy()
        pos_with_hour["hour"] = pos_with_hour["report_time"].dt.floor("h").dt.hour
        pos_with_hour["phase"] = pos_with_hour["flight_phase"].fillna("UNKNOWN")

        pivot = pos_with_hour.groupby(["hour", "phase"]).size().unstack(fill_value=0)
        # Normalize to 100%
        row_sums = pivot.sum(axis=1)
        pivot_pct = pivot.div(row_sums, axis=0) * 100

        hours = np.arange(24)
        bottoms = np.zeros(24)
        for phase in sorted(pivot_pct.columns):
            vals = np.array([pivot_pct.at[h, phase] if h in pivot_pct.index else 0 for h in hours])
            color = PHASE_COLORS.get(phase, "#7f8c8d")
            ax2.fill_between(hours, bottoms, bottoms + vals, label=phase, alpha=0.8, color=color, step="post")
            bottoms += vals

        ax2.set_xlim(0, 23)
        ax2.set_ylim(0, 100)
        ax2.set_xlabel("Hour (UTC)")
        ax2.set_ylabel("Phase Proportion (%)")
        ax2.set_title("Phase by Hour (Normalized)")
        ax2.legend(fontsize=7, loc="upper right")
        ax2.grid(axis="y", alpha=0.4)
    else:
        ax2.text(0.5, 0.5, "Insufficient data", ha="center", va="center", color=TEXT_COLOR)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 5 done")


def page6_airline_mix(pdf, report_date, positions_df, sessions_df):
    fig, axes = plt.subplots(1, 3, figsize=(11, 8.5))
    fig.patch.set_facecolor(DARK_BG)
    add_page_header(fig, report_date, "Airline & Aircraft Mix")
    fig.subplots_adjust(top=0.91, bottom=0.12, left=0.07, right=0.97, wspace=0.5)

    # --- Callsign prefix breakdown (from sessions) ---
    ax = axes[0]
    if not sessions_df.empty:
        sessions_df = sessions_df.copy()
        sessions_df["prefix"] = sessions_df["callsign"].apply(extract_callsign_prefix)
        prefix_counts = sessions_df["prefix"].value_counts().head(15)
        colors = [PHASE_COLORS.get("CRZ", "#3498db")] * len(prefix_counts)
        ax.barh(prefix_counts.index[::-1], prefix_counts.values[::-1], color=colors, alpha=0.85)
    ax.set_xlabel("Sessions")
    ax.set_title("Top 15 Callsign Prefixes")
    ax.grid(axis="x", alpha=0.5)

    # --- Category distribution ---
    ax2 = axes[1]
    cat = positions_df["category"].fillna("NULL")
    null_pct = (cat == "NULL").sum() / len(cat) * 100 if len(cat) > 0 else 100
    cat_counts = cat.value_counts().head(10)
    ax2.bar(range(len(cat_counts)), cat_counts.values, color="#9b59b6", alpha=0.85)
    ax2.set_xticks(range(len(cat_counts)))
    ax2.set_xticklabels(cat_counts.index, rotation=45, ha="right", fontsize=7)
    ax2.set_ylabel("Report Count")
    ax2.set_title("Emitter Category Distribution")
    ax2.grid(axis="y", alpha=0.5)
    if null_pct > 80:
        ax2.text(
            0.5, 0.92,
            "emitter category not widely populated",
            transform=ax2.transAxes, ha="center", color=TEXT_COLOR, fontsize=7, style="italic",
        )

    # --- Commercial/GA/Military/Unknown pie ---
    ax3 = axes[2]
    if not sessions_df.empty:
        # NOTE: squawk-based military classification not yet implemented;
        # requires per-report squawk aggregation. Callsign-only classification for now.
        sessions_df["flight_class"] = sessions_df["callsign"].apply(
            lambda cs: classify_flight(cs)
        )
        class_counts = sessions_df["flight_class"].value_counts()
        class_colors = {"Commercial": "#3498db", "GA": "#2ecc71", "Military": "#e74c3c", "Unknown": "#7f8c8d"}
        colors = [class_colors.get(c, "#aaa") for c in class_counts.index]
        wedges, texts, autotexts = ax3.pie(
            class_counts.values,
            labels=class_counts.index,
            colors=colors,
            autopct="%1.1f%%",
            pctdistance=0.75,
            startangle=90,
        )
        for t in texts + autotexts:
            t.set_color(TEXT_COLOR)
            t.set_fontsize(8)
    ax3.set_title("Flight Classification")

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 6 done")


def page7_session_quality(pdf, report_date, sessions_df, positions_df):
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(DARK_BG)
    add_page_header(fig, report_date, "Session Quality & Top Aircraft")
    fig.subplots_adjust(top=0.91, bottom=0.08, left=0.08, right=0.97, hspace=0.5)

    ax_dur = fig.add_subplot(2, 2, 1)
    ax_stat = fig.add_subplot(2, 2, 2)
    ax_table = fig.add_subplot(2, 1, 2)
    ax_table.set_axis_off()

    # --- Session duration histogram ---
    if not sessions_df.empty:
        closed = sessions_df.dropna(subset=["ended_at"]).copy()
        if not closed.empty:
            durations = (closed["ended_at"] - closed["started_at"]).dt.total_seconds() / 60
            durations_clipped = durations[(durations >= 0) & (durations <= 300)]
            if len(durations_clipped) == 0:
                ax_dur.text(0.5, 0.5, "No sessions in range", ha="center", va="center", color=TEXT_COLOR)
            else:
                bins = np.arange(0, 305, 5)
                ax_dur.hist(durations_clipped, bins=bins, color=ACCENT, alpha=0.85, edgecolor="none")
                med = durations_clipped.median()
                mean = durations_clipped.mean()
                p95 = durations_clipped.quantile(0.95)
                ax_dur.axvline(med, color=HIGHLIGHT, linestyle="--", linewidth=1.2, label=f"Median: {med:.1f}m")
                ax_dur.axvline(mean, color="#2ecc71", linestyle=":", linewidth=1.2, label=f"Mean: {mean:.1f}m")
                ax_dur.axvline(p95, color="#e74c3c", linestyle=":", linewidth=1.2, label=f"P95: {p95:.1f}m")
                ax_dur.legend(fontsize=7)
        else:
            ax_dur.text(0.5, 0.5, "No closed sessions", ha="center", va="center", color=TEXT_COLOR)
    ax_dur.set_xlabel("Duration (min)")
    ax_dur.set_ylabel("Count")
    ax_dur.set_title("Session Duration Distribution")
    ax_dur.grid(axis="y", alpha=0.5)

    # --- Trajectory completeness stat ---
    ax_stat.set_axis_off()
    if not sessions_df.empty:
        closed = sessions_df.dropna(subset=["ended_at"])
        total_closed = len(closed)
        with_traj = int(closed["has_trajectory"].sum()) if not closed.empty else 0
        pct = with_traj / total_closed * 100 if total_closed > 0 else 0
        ax_stat.text(
            0.5, 0.65,
            f"{with_traj} of {total_closed}",
            ha="center", va="center", fontsize=22, fontweight="bold", color=ACCENT,
        )
        ax_stat.text(
            0.5, 0.45,
            "closed sessions have\nmaterialized trajectories",
            ha="center", va="center", fontsize=11, color=TEXT_COLOR,
        )
        ax_stat.text(
            0.5, 0.28,
            f"({pct:.1f}%)",
            ha="center", va="center", fontsize=16, color=HIGHLIGHT,
        )

    # --- Top 15 aircraft table ---
    if not positions_df.empty:
        report_counts = positions_df.groupby("hex").agg(
            reports=("hex", "count"),
        ).reset_index()

        # Get callsign from sessions
        if not sessions_df.empty:
            hex_callsign = sessions_df.groupby("hex")["callsign"].first().reset_index()
            hex_callsign.columns = ["hex", "callsign_name"]
            hex_dur = sessions_df.copy()
            hex_dur["duration_min"] = (
                (hex_dur["ended_at"] - hex_dur["started_at"]).dt.total_seconds() / 60
            )
            hex_dur_agg = hex_dur.groupby("hex").agg(
                total_duration=("duration_min", "sum"),
                total_distance=("total_distance_nm", "sum"),
            ).reset_index()

            report_counts = report_counts.merge(hex_callsign, on="hex", how="left")
            report_counts = report_counts.merge(hex_dur_agg, on="hex", how="left")
            report_counts = report_counts.sort_values("reports", ascending=False).head(15).reset_index(drop=True)

            # Phases per hex
            hex_phases = positions_df.groupby("hex")["flight_phase"].apply(
                lambda x: "/".join(sorted(x.dropna().unique()))
            ).reset_index()
            hex_phases.columns = ["hex", "phases"]
            report_counts = report_counts.merge(hex_phases, on="hex", how="left")

            table_data = []
            col_labels = ["#", "Hex", "Callsign", "Reports", "Duration(m)", "Distance(NM)", "Phases"]
            for i, row in report_counts.iterrows():
                table_data.append([
                    str(i + 1),
                    str(row.get("hex", "")),
                    str(row.get("callsign_name", ""))[:8] if pd.notna(row.get("callsign_name")) else "",
                    f"{int(row.get('reports', 0)):,}",
                    f"{row.get('total_duration', 0):.0f}" if pd.notna(row.get("total_duration")) else "",
                    f"{row.get('total_distance', 0):.0f}" if pd.notna(row.get("total_distance")) else "",
                    str(row.get("phases", ""))[:20] if pd.notna(row.get("phases")) else "",
                ])

            if table_data:
                tbl = ax_table.table(
                    cellText=table_data,
                    colLabels=col_labels,
                    loc="center",
                    cellLoc="center",
                )
                tbl.auto_set_font_size(False)
                tbl.set_fontsize(7.5)
                tbl.scale(1, 1.4)
                # Style header
                for j in range(len(col_labels)):
                    tbl[0, j].set_facecolor(ACCENT)
                    tbl[0, j].set_text_props(color="white", fontweight="bold")
                # Style rows
                for i in range(1, len(table_data) + 1):
                    for j in range(len(col_labels)):
                        tbl[i, j].set_facecolor(PANEL_BG if i % 2 == 0 else "#1e1e3a")
                        tbl[i, j].set_text_props(color=TEXT_COLOR)

    ax_table.set_title("Top 15 Aircraft by Report Count", pad=10)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 7 done")


def page8_data_quality(pdf, report_date, per_min_df, null_df, partition_df, db_size_str, gaps):
    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor(DARK_BG)
    add_page_header(fig, report_date, "Data Quality & System Health")
    fig.subplots_adjust(top=0.91, bottom=0.07, left=0.08, right=0.97, hspace=0.55)

    ax_ingest = fig.add_subplot(3, 1, 1)
    ax_null = fig.add_subplot(3, 2, 3)
    ax_info = fig.add_subplot(3, 2, 4)
    ax_info.set_axis_off()

    # --- Ingest rate time series ---
    if not per_min_df.empty:
        ax_ingest.plot(
            per_min_df["minute"], per_min_df["reports"],
            color="#3498db", linewidth=0.6, alpha=0.9,
        )
        ax_ingest.fill_between(per_min_df["minute"], per_min_df["reports"], alpha=0.2, color="#3498db")
        for gap in gaps:
            ax_ingest.axvspan(gap["start"], gap["end"], alpha=0.3, color="#e74c3c", zorder=2)
            ax_ingest.annotate(
                f"Gap\n{gap['duration_min']}m",
                xy=(gap["start"] + (gap["end"] - gap["start"]) / 2, 0),
                xytext=(0, 20), textcoords="offset points",
                ha="center", color=ACCENT, fontsize=7,
                arrowprops=dict(arrowstyle="->", color=ACCENT, lw=0.8),
            )
    ax_ingest.set_ylabel("Reports / min")
    ax_ingest.set_title("Ingest Rate (Reports per Minute)")
    ax_ingest.grid(alpha=0.4)
    ax_ingest.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%H:%M"))
    ax_ingest.tick_params(axis="x", rotation=45, labelsize=7)

    # --- NULL rate bar chart ---
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
        bar_colors = [ACCENT if p > 20 else "#2ecc71" for p in pcts]
        ax_null.barh(cols, pcts, color=bar_colors, alpha=0.85)
        ax_null.set_xlabel("% NULL")
        ax_null.set_xlim(0, 100)
        ax_null.set_title("NULL Rates by Column")
        ax_null.grid(axis="x", alpha=0.5)
        for i, pct in enumerate(pcts):
            ax_null.text(pct + 0.5, i, f"{pct:.1f}%", va="center", color=TEXT_COLOR, fontsize=8)

    # --- Partition sizes + DB size ---
    info_lines = [f"Database total size: {db_size_str}", ""]
    if not partition_df.empty:
        info_lines.append("Active Partition Sizes:")
        for _, row in partition_df.iterrows():
            info_lines.append(f"  {row['partition_name']:40s}  {row['total_size']}")
    else:
        info_lines.append("No partition size data available.")

    ax_info.text(
        0.02, 0.98, "\n".join(info_lines),
        va="top", ha="left",
        color=TEXT_COLOR, fontsize=8,
        fontfamily="monospace",
        transform=ax_info.transAxes,
        bbox=dict(boxstyle="round", facecolor=PANEL_BG, edgecolor=GRID_COLOR),
    )
    ax_info.set_title("Partition & DB Sizes", pad=8)

    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] Page 8 done")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Planegraph daily station report generator")
    parser.add_argument("--date", help="Report date YYYY-MM-DD (default: yesterday UTC)")
    parser.add_argument("--station-lat", type=float, default=None)
    parser.add_argument("--station-lon", type=float, default=None)
    parser.add_argument("--output-dir", default="/opt/planegraph/reports/daily")
    return parser.parse_args()


def main():
    args = parse_args()
    ts = datetime.now(timezone.utc)

    # --- DATABASE_URL check ---
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
        sys.exit(3)

    # --- Report date ---
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

    print(f"[{ts.strftime('%H:%M:%S')}] Planegraph Daily Report — {report_date}")
    print(f"[{ts.strftime('%H:%M:%S')}] Data window: {day_start} — {day_end}")

    # --- Station coordinates ---
    station_lat = args.station_lat
    station_lon = args.station_lon
    if station_lat is None:
        station_lat_str = os.environ.get("STATION_LAT")
        if station_lat_str:
            try:
                station_lat = float(station_lat_str)
            except ValueError:
                pass
    if station_lon is None:
        station_lon_str = os.environ.get("STATION_LON")
        if station_lon_str:
            try:
                station_lon = float(station_lon_str)
            except ValueError:
                pass
    if station_lat is None or station_lon is None:
        print(f"[{ts.strftime('%H:%M:%S')}] Station coordinates not available — range plots will be skipped.")
        station_lat = station_lon = None

    # --- Database connection ---
    try:
        conn = get_connection(database_url)
    except Exception as exc:
        print(f"ERROR: Database connection failed: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        # --- Load summary data ---
        print(f"[{ts.strftime('%H:%M:%S')}] Loading data from database...")
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

        print(f"[{ts.strftime('%H:%M:%S')}] Loading position reports (may take a moment)...")
        positions_df = load_positions(conn, day_start, day_end)

        # Ensure timezone-aware datetimes in DataFrames
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

        print(f"[{ts.strftime('%H:%M:%S')}] {len(positions_df):,} position reports loaded.")

        # Cast numeric columns to Python float (psycopg2 may return decimal.Decimal)
        for col in ["lat", "lon", "alt_ft", "track", "speed_kts", "vrate_fpm"]:
            if col in positions_df.columns:
                positions_df[col] = pd.to_numeric(positions_df[col], errors="coerce")

        # --- Gap detection ---
        gaps = detect_gaps(hourly_df, day_start)
        if gaps:
            print(f"[{ts.strftime('%H:%M:%S')}] {len(gaps)} data gap(s) detected.")

        # --- Output path ---
        out_path = output_path(args.output_dir, report_date)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"[{ts.strftime('%H:%M:%S')}] Writing report to {out_path}")

        # --- Apply style ---
        apply_dark_style()

        # --- Generate PDF ---
        with PdfPages(str(out_path)) as pdf:
            page1_executive_summary(pdf, report_date, summary, hourly_df, sessions_df, gaps, day_start, day_end, ts)
            page2_temporal_profile(pdf, report_date, hourly_df, concurrent_df, gaps, day_start)
            page3_altitude_speed(pdf, report_date, positions_df)
            page4_spatial(pdf, report_date, positions_df, airports_df, station_lat, station_lon)
            page5_flight_phase(pdf, report_date, positions_df, hourly_df)
            page6_airline_mix(pdf, report_date, positions_df, sessions_df)
            page7_session_quality(pdf, report_date, sessions_df, positions_df)
            page8_data_quality(pdf, report_date, per_min_df, null_df, partition_df, db_size_str, gaps)

        size_kb = out_path.stat().st_size // 1024
        print(f"[{ts.strftime('%H:%M:%S')}] Report complete: {out_path} ({size_kb:,} KB)")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
