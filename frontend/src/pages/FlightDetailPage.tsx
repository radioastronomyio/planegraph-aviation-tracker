import { useState, useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { FlightMap } from "../components/FlightMap";
import type { TrackPoint } from "../types/analytics";
import { fetchJson } from "../utils/api";
import styles from "./FlightDetailPage.module.css";

interface FlightDetail {
  session_id: string;
  hex: string;
  callsign: string | null;
  started_at: string;
  ended_at: string | null;
  on_ground: boolean;
  total_distance_nm: number | null;
  departure_airport_icao: string | null;
  arrival_airport_icao: string | null;
  trajectory: Record<string, unknown> | null;
}

function formatDuration(startedAt: string, endedAt: string | null): string {
  if (!endedAt) return "In progress";
  const secs = Math.round((new Date(endedAt).getTime() - new Date(startedAt).getTime()) / 1000);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function timeLabel(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function FlightDetailPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [flight, setFlight] = useState<FlightDetail | null>(null);
  const [track, setTrack] = useState<TrackPoint[]>([]);
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    Promise.all([
      fetchJson<FlightDetail>(`/api/v1/flights/${sessionId}`),
      fetchJson<TrackPoint[]>(`/api/v1/flights/${sessionId}/track`),
    ])
      .then(([f, t]) => {
        setFlight(f);
        setTrack(t);
      })
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [sessionId]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function handleMouseMove(data: any) {
    if (data && typeof data.activeTooltipIndex === "number") {
      setFocusIndex(data.activeTooltipIndex);
    }
  }

  function handleMouseLeave() {
    setFocusIndex(null);
  }

  function togglePlay() {
    if (playing) {
      if (playIntervalRef.current) clearInterval(playIntervalRef.current);
      setPlaying(false);
      setFocusIndex(null);
    } else {
      let idx = focusIndex ?? 0;
      setPlaying(true);
      playIntervalRef.current = setInterval(() => {
        idx += 1;
        if (idx >= track.length) {
          if (playIntervalRef.current) clearInterval(playIntervalRef.current);
          setPlaying(false);
          setFocusIndex(null);
          return;
        }
        setFocusIndex(idx);
      }, 100); // ~10 pts/sec
    }
  }

  // Cleanup interval on unmount
  useEffect(() => {
    return () => {
      if (playIntervalRef.current) clearInterval(playIntervalRef.current);
    };
  }, []);

  if (loading) {
    return (
      <div className={styles.page} data-testid="flight-detail-page">
        <p className={styles.loadingMsg}>Loading flight…</p>
      </div>
    );
  }

  if (error || !flight) {
    return (
      <div className={styles.page} data-testid="flight-detail-page">
        <Link to="/flights" className={styles.backLink}>← Back to Flights</Link>
        <p className={styles.errorMsg}>{error ?? "Flight not found"}</p>
      </div>
    );
  }

  const hasApproach = track.some((pt) => pt.phase === "APP" || pt.phase === "LDG");

  const tooltipStyle = { background: "#1a1d27", border: "1px solid #333", color: "#e0e0e0" };

  return (
    <div className={styles.page} data-testid="flight-detail-page">
      <div className={styles.topBar}>
        <Link to="/flights" className={styles.backLink}>← Back to Flights</Link>
        {hasApproach && (
          <Link to={`/flights/${sessionId}/approach`} className={styles.approachLink}>
            Approach Analysis →
          </Link>
        )}
      </div>

      <div className={styles.layout}>
        {/* Left: Map panel */}
        <div className={styles.mapPanel}>
          <FlightMap trackPoints={track} focusIndex={focusIndex} />
        </div>

        {/* Right: Metadata + charts */}
        <div className={styles.infoPanel}>
          <div className={styles.metaCard}>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Callsign</span>
              <span className={styles.metaValue}>{flight.callsign ?? "—"}</span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>ICAO Hex</span>
              <span className={styles.mono}>{flight.hex.toUpperCase()}</span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Started</span>
              <span className={styles.metaValue}>{new Date(flight.started_at).toLocaleString()}</span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Duration</span>
              <span className={styles.metaValue}>{formatDuration(flight.started_at, flight.ended_at)}</span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Distance</span>
              <span className={styles.metaValue}>
                {flight.total_distance_nm != null ? `${flight.total_distance_nm.toFixed(1)} nm` : "—"}
              </span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Dep / Arr</span>
              <span className={styles.mono}>
                {flight.departure_airport_icao ?? "?"} / {flight.arrival_airport_icao ?? "?"}
              </span>
            </div>
            <div className={styles.metaRow}>
              <span className={styles.metaLabel}>Status</span>
              <span className={styles.metaValue}>{flight.on_ground ? "Ground" : "Airborne"}</span>
            </div>
          </div>

          <div className={styles.playBar}>
            <button className={styles.playBtn} onClick={togglePlay} data-testid="play-btn">
              {playing ? "⏸ Pause" : "▶ Play"}
            </button>
            <span className={styles.playInfo}>
              {focusIndex != null ? `Point ${focusIndex + 1} / ${track.length}` : `${track.length} points`}
            </span>
          </div>

          <div className={styles.charts}>
            <div className={styles.chartBlock}>
              <h3>Altitude (ft)</h3>
              <ResponsiveContainer width="100%" height={130}>
                <LineChart
                  data={track}
                  syncId="flight-replay"
                  onMouseMove={handleMouseMove}
                  onMouseLeave={handleMouseLeave}
                  margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                >
                  <XAxis dataKey="timestamp" tickFormatter={timeLabel} tick={{ fill: "#aaa", fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: "#aaa", fontSize: 10 }} width={48} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => typeof v === "string" ? timeLabel(v) : String(v)} />
                  <Line type="monotone" dataKey="alt_ft" stroke="#3b82f6" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className={styles.chartBlock}>
              <h3>Speed (kts)</h3>
              <ResponsiveContainer width="100%" height={130}>
                <LineChart
                  data={track}
                  syncId="flight-replay"
                  onMouseMove={handleMouseMove}
                  onMouseLeave={handleMouseLeave}
                  margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                >
                  <XAxis dataKey="timestamp" tickFormatter={timeLabel} tick={{ fill: "#aaa", fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: "#aaa", fontSize: 10 }} width={40} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => typeof v === "string" ? timeLabel(v) : String(v)} />
                  <Line type="monotone" dataKey="speed_kts" stroke="#22c55e" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <div className={styles.chartBlock}>
              <h3>Vertical Rate (fpm)</h3>
              <ResponsiveContainer width="100%" height={130}>
                <LineChart
                  data={track}
                  syncId="flight-replay"
                  onMouseMove={handleMouseMove}
                  onMouseLeave={handleMouseLeave}
                  margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                >
                  <XAxis dataKey="timestamp" tickFormatter={timeLabel} tick={{ fill: "#aaa", fontSize: 10 }} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: "#aaa", fontSize: 10 }} width={48} />
                  <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => typeof v === "string" ? timeLabel(v) : String(v)} />
                  <ReferenceLine y={0} stroke="#444" strokeDasharray="4 2" />
                  <Line type="monotone" dataKey="vrate_fpm" stroke="#a855f7" dot={false} strokeWidth={1.5} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
