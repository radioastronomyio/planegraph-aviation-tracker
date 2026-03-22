import { useState, useEffect } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { AirportSummary, RunwayUtilization, AirportHourlyPoint } from "../types/analytics";
import { fetchJson } from "../utils/api";
import styles from "./AirportsPage.module.css";

const HOURS_OPTIONS = [24, 48, 72, 168];
const AIRPORTS = ["KCMH", "KLCK", "KOSU", "KTZR"];
const tooltipStyle = { background: "#1a1d27", border: "1px solid #333", color: "#e0e0e0" };

export function AirportsPage() {
  const [hours, setHours] = useState(24);
  const [selectedAirport, setSelectedAirport] = useState("KCMH");
  const [summary, setSummary] = useState<AirportSummary[]>([]);
  const [runwayUtil, setRunwayUtil] = useState<RunwayUtilization[]>([]);
  const [hourly, setHourly] = useState<AirportHourlyPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetchJson<AirportSummary[]>(`/api/v1/analytics/airports/summary?hours=${hours}`),
      fetchJson<RunwayUtilization[]>(`/api/v1/analytics/airports/runway-utilization?hours=${hours}`),
      fetchJson<AirportHourlyPoint[]>(`/api/v1/analytics/airports/hourly?icao=${selectedAirport}&hours=${hours}`),
    ])
      .then(([s, r, h]) => {
        setSummary(s);
        setRunwayUtil(r);
        setHourly(h);
      })
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [hours, selectedAirport]);

  return (
    <div className={styles.page} data-testid="airports-page">
      <h1>Airport Analytics</h1>

      <div className={styles.controls}>
        <div className={styles.controlGroup}>
          <label className={styles.controlLabel}>Time window:</label>
          <div className={styles.btnGroup}>
            {HOURS_OPTIONS.map((h) => (
              <button
                key={h}
                className={hours === h ? styles.btnActive : styles.btn}
                onClick={() => setHours(h)}
                data-testid={`hours-btn-${h}`}
              >
                {h < 24 ? `${h}h` : `${h / 24}d`}
              </button>
            ))}
          </div>
        </div>
        <div className={styles.controlGroup}>
          <label className={styles.controlLabel}>Airport:</label>
          <div className={styles.btnGroup}>
            {AIRPORTS.map((ap) => (
              <button
                key={ap}
                className={selectedAirport === ap ? styles.btnActive : styles.btn}
                onClick={() => setSelectedAirport(ap)}
                data-testid={`airport-btn-${ap}`}
              >
                {ap}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <p className={styles.errorMsg}>Error: {error}</p>}

      {/* Airport summary cards */}
      <div className={styles.statsGrid} data-testid="airport-summary-grid">
        {summary.slice(0, 8).map((ap) => (
          <div key={ap.icao} className={styles.statCard} data-testid={`airport-card-${ap.icao}`}>
            <span className={styles.statCode}>{ap.icao}</span>
            <span className={styles.statName}>{ap.name}</span>
            <div className={styles.statCounts}>
              <span className={styles.statArr} title="Arrivals">↓ {ap.arrivals}</span>
              <span className={styles.statDep} title="Departures">↑ {ap.departures}</span>
              <span className={styles.statTotal}>{ap.arrivals + ap.departures} total</span>
            </div>
          </div>
        ))}
        {!loading && summary.length === 0 && (
          <p className={styles.empty}>No airport activity in this window.</p>
        )}
      </div>

      <div className={styles.twoCol}>
        {/* Runway utilization */}
        <section className={styles.section}>
          <h2>Runway Utilization</h2>
          {runwayUtil.length > 0 ? (
            <div className={styles.chartWrap}>
              <ResponsiveContainer width="100%" height={Math.max(180, runwayUtil.length * 32)}>
                <BarChart
                  data={runwayUtil}
                  layout="vertical"
                  margin={{ top: 4, right: 16, bottom: 0, left: 64 }}
                >
                  <XAxis type="number" tick={{ fill: "#aaa", fontSize: 11 }} allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey={(d: RunwayUtilization) => `${d.airport_icao} ${d.designator}`}
                    tick={{ fill: "#aaa", fontSize: 11 }}
                    width={64}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(v) => [v, "flights"]}
                  />
                  <Bar dataKey="flight_count" radius={[0, 3, 3, 0]}>
                    {runwayUtil.map((_, i) => (
                      <Cell key={i} fill="#3b82f6" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className={styles.empty}>No runway data available.</p>
          )}
        </section>

        {/* Hourly activity */}
        <section className={styles.section}>
          <h2>Hourly Activity — {selectedAirport}</h2>
          <div className={styles.chartWrap} data-testid="hourly-chart">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={hourly}
                margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
              >
                <XAxis
                  dataKey="hour_start"
                  tickFormatter={(v: string) =>
                    new Date(v).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
                  }
                  tick={{ fill: "#aaa", fontSize: 10 }}
                  interval="preserveStartEnd"
                />
                <YAxis allowDecimals={false} tick={{ fill: "#aaa", fontSize: 11 }} width={28} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  labelFormatter={(v) => typeof v === "string" ? new Date(v).toLocaleString() : String(v)}
                  formatter={(v) => [v, "flights"]}
                />
                <Bar dataKey="flight_count" fill="#7eb8f7" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>
    </div>
  );
}
