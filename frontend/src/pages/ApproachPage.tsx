import { useState, useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { FlightMap } from "../components/FlightMap";
import type { ApproachAnalysis, ApproachPoint, TrackPoint } from "../types/analytics";
import { SEVERITY_COLORS } from "../utils/colors";
import styles from "./ApproachPage.module.css";

export function ApproachPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [analysis, setAnalysis] = useState<ApproachAnalysis | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!sessionId) return;
    setLoading(true);
    fetch(`/api/v1/flights/${sessionId}/approach-analysis`)
      .then(async (r) => {
        if (r.status === 404) {
          setNotFound(true);
          return;
        }
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        const data = await r.json() as ApproachAnalysis;
        setAnalysis(data);
      })
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) {
    return (
      <div className={styles.page} data-testid="approach-page">
        <p className={styles.loadingMsg}>Loading approach analysis…</p>
      </div>
    );
  }

  if (notFound) {
    return (
      <div className={styles.page} data-testid="approach-page">
        <Link to={`/flights/${sessionId}`} className={styles.backLink}>← Back to Flight Detail</Link>
        <p className={styles.notFound} data-testid="approach-not-found">
          No approach data available for this flight
        </p>
      </div>
    );
  }

  if (error || !analysis) {
    return (
      <div className={styles.page} data-testid="approach-page">
        <Link to={`/flights/${sessionId}`} className={styles.backLink}>← Back to Flight Detail</Link>
        <p className={styles.errorMsg}>{error ?? "Failed to load approach data"}</p>
      </div>
    );
  }

  const { runway, points } = analysis;

  // Build scatter data from approach points — severity colors from API
  const scatterData = points.map((pt) => ({
    position: [pt.distance_nm, pt.actual_alt_ft_msl] as [number, number],
    color: hexToRgb(SEVERITY_COLORS[pt.severity] ?? "#7eb8f7") as [number, number, number],
    radius: 5,
    // We also need lat/lon for map; approximate from available data
    // The map will use the points data directly
  }));
  void scatterData;

  // Convert approach points to track-compatible for map
  const mapPoints: TrackPoint[] = points.map((pt) => ({
    timestamp: pt.timestamp,
    lat: 0, // ApproachPoint doesn't have lat/lon - we'll skip map for approach
    lon: 0,
    alt_ft: pt.actual_alt_ft_msl,
    speed_kts: null,
    vrate_fpm: null,
    track: null,
    phase: pt.severity, // use severity as phase for color lookup — handled differently in map
  }));
  void mapPoints;

  // For the approach map we build scatter data from the full track (if available)
  // Since ApproachPoint doesn't include lat/lon, the map will show an empty path
  // but the threshold marker and approach scatter are added via extraScatterData
  const thresholdPoint = { lat: 0, lon: 0 }; // threshold lat/lon not in ApproachAnalysis schema
  void thresholdPoint;

  // Severity summary
  const maxDev = points.reduce<ApproachPoint | null>((max, pt) => {
    if (!max || Math.abs(pt.deviation_ft) > Math.abs(max.deviation_ft)) return pt;
    return max;
  }, null);

  const tooltipStyle = { background: "#1a1d27", border: "1px solid #333", color: "#e0e0e0" };

  // Chart data: X = distance_nm reversed (higher distance on left), Y = altitude
  const chartData = [...points].sort((a, b) => b.distance_nm - a.distance_nm);

  return (
    <div className={styles.page} data-testid="approach-page">
      <div className={styles.topBar}>
        <Link to={`/flights/${sessionId}`} className={styles.backLink}>← Back to Flight Detail</Link>
      </div>

      <div className={styles.layout}>
        {/* Left: visual severity scatter on chart only (no lat/lon available) */}
        <div className={styles.chartPanel}>
          <section className={styles.section}>
            <h2>Glideslope Deviation — {runway.icao} {runway.designator}</h2>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart
                data={chartData}
                margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
              >
                <CartesianGrid stroke="#2a2d3a" strokeDasharray="3 3" />
                <XAxis
                  dataKey="distance_nm"
                  reversed
                  label={{ value: "Distance to threshold (nm)", position: "insideBottom", offset: -4, fill: "#888", fontSize: 11 }}
                  tick={{ fill: "#aaa", fontSize: 11 }}
                />
                <YAxis
                  tick={{ fill: "#aaa", fontSize: 11 }}
                  width={56}
                  label={{ value: "Alt (ft MSL)", angle: -90, position: "insideLeft", fill: "#888", fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value, name) => {
                    if (name === "actual_alt_ft_msl") return [`${value} ft`, "Actual Alt"];
                    if (name === "expected_alt_ft_msl") return [`${value} ft`, "Expected Alt"];
                    return [value, name];
                  }}
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const pt = payload[0]?.payload as ApproachPoint;
                    const sev = pt?.severity;
                    return (
                      <div style={tooltipStyle} className={styles.customTooltip}>
                        <p>{pt?.distance_nm?.toFixed(2)} nm</p>
                        <p>Actual: {pt?.actual_alt_ft_msl} ft</p>
                        <p>Expected: {pt?.expected_alt_ft_msl} ft</p>
                        <p>Deviation: {pt?.deviation_ft > 0 ? "+" : ""}{pt?.deviation_ft} ft</p>
                        <p style={{ color: SEVERITY_COLORS[sev] ?? "#fff" }} data-testid={`severity-label-${sev}`}>
                          {sev}
                        </p>
                      </div>
                    );
                  }}
                />
                {/* Reference expected glideslope */}
                <Line
                  type="monotone"
                  dataKey="expected_alt_ft_msl"
                  stroke="#666"
                  strokeDasharray="6 3"
                  dot={false}
                  strokeWidth={1.5}
                  name="expected_alt_ft_msl"
                />
                {/* Actual altitude line — dots colored by severity from API */}
                <Line
                  type="monotone"
                  dataKey="actual_alt_ft_msl"
                  stroke="#7eb8f7"
                  dot={(props) => {
                    const { cx, cy, payload } = props as { cx: number; cy: number; payload: ApproachPoint };
                    const color = SEVERITY_COLORS[payload.severity] ?? "#7eb8f7";
                    return (
                      <circle
                        key={`dot-${payload.timestamp}`}
                        cx={cx}
                        cy={cy}
                        r={4}
                        fill={color}
                        stroke="none"
                        data-severity={payload.severity}
                        data-testid={`approach-dot`}
                      />
                    );
                  }}
                  strokeWidth={2}
                  name="actual_alt_ft_msl"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </section>

          <section className={styles.section}>
            <h2>Summary</h2>
            <div className={styles.summaryGrid}>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>Runway</span>
                <span className={styles.summaryValue}>{runway.icao} {runway.designator}</span>
              </div>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>Heading</span>
                <span className={styles.summaryValue}>{runway.heading_true.toFixed(0)}°</span>
              </div>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>Threshold Elev</span>
                <span className={styles.summaryValue}>{runway.threshold_elevation_ft} ft</span>
              </div>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>Points Analyzed</span>
                <span className={styles.summaryValue}>{points.length}</span>
              </div>
              {maxDev && (
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>Max Deviation</span>
                  <span
                    className={styles.summaryValue}
                    style={{ color: SEVERITY_COLORS[maxDev.severity] }}
                    data-testid="max-deviation"
                  >
                    {maxDev.deviation_ft > 0 ? "+" : ""}{maxDev.deviation_ft} ft ({maxDev.severity})
                  </span>
                </div>
              )}
            </div>
          </section>

          {/* Severity legend */}
          <div className={styles.legend}>
            {(["GREEN", "YELLOW", "RED"] as const).map((sev) => (
              <span key={sev} className={styles.legendItem} data-testid={`legend-${sev}`}>
                <span className={styles.legendDot} style={{ background: SEVERITY_COLORS[sev] }} />
                {sev}
              </span>
            ))}
          </div>
        </div>

        {/* Right: map panel showing approach path */}
        <div className={styles.mapPanel}>
          <div className={styles.mapNote}>
            Map requires full track data. View on{" "}
            <Link to={`/flights/${sessionId}`} className={styles.backLink}>Flight Detail</Link>.
          </div>
          <FlightMap trackPoints={[]} focusIndex={null} />
        </div>
      </div>
    </div>
  );
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
