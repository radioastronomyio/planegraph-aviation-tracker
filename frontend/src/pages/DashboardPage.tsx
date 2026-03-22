import { useEffect, useState } from "react";

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json() as Promise<T>;
}
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import styles from "./DashboardPage.module.css";

interface Stats {
  active_aircraft: number;
  flights_today: number;
  flights_in_last_hour: number;
  ingest_rate_per_sec: number;
  materializer_lag_sec: number | null;
  storage_bytes: number | null;
  oldest_data_date: string | null;
}

interface Health {
  status: string;
  postgres: string;
  ultrafeeder: string;
  ingest_active: boolean;
  last_position_report: string | null;
}

interface HourlyPoint {
  hour_start: string;
  flight_count: number;
}

interface PhaseEntry {
  phase: string;
  count: number;
}

interface TopAircraftEntry {
  hex: string;
  callsign: string | null;
  flight_count: number;
}

const PHASE_COLORS: Record<string, string> = {
  GND: "#64748b",
  TOF: "#f59e0b",
  CLB: "#22c55e",
  CRZ: "#3b82f6",
  DES: "#a855f7",
  APP: "#f97316",
  LDG: "#ef4444",
  UNKNOWN: "#6b7280",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function StatusDot({ status }: { status: string }) {
  const ok = status === "healthy";
  return <span className={ok ? styles.dotGreen : styles.dotRed} title={status} />;
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className={styles.statCard}>
      <span className={styles.statLabel}>{label}</span>
      <span className={styles.statValue}>{value}</span>
      {sub && <span className={styles.statSub}>{sub}</span>}
    </div>
  );
}

export function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [hourly, setHourly] = useState<HourlyPoint[]>([]);
  const [phases, setPhases] = useState<PhaseEntry[]>([]);
  const [topAircraft, setTopAircraft] = useState<TopAircraftEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const BASE = "/api/v1";

    function loadAll() {
      Promise.all([
        fetchJson<Stats>(`${BASE}/stats`),
        fetchJson<Health>(`${BASE}/health`),
        fetchJson<HourlyPoint[]>(`${BASE}/stats/hourly?hours=24`),
        fetchJson<PhaseEntry[]>(`${BASE}/stats/phases`),
        fetchJson<TopAircraftEntry[]>(`${BASE}/stats/top-aircraft?limit=20`),
      ])
        .then(([s, h, ho, ph, ta]) => {
          setStats(s);
          setHealth(h);
          setHourly(ho);
          setPhases(ph);
          setTopAircraft(ta);
        })
        .catch((e: unknown) => setError(String(e)));
    }

    loadAll();
    const interval = setInterval(() => {
      fetchJson<Stats>(`${BASE}/stats`)
        .then((s) => setStats(s))
        .catch(() => {});
      fetchJson<Health>(`${BASE}/health`)
        .then((h) => setHealth(h))
        .catch(() => {});
    }, 10_000);

    return () => clearInterval(interval);
  }, []);

  if (error) {
    return (
      <div className={styles.page} data-testid="dashboard-page">
        <h1>Dashboard</h1>
        <p className={styles.errorMsg}>Failed to load dashboard: {error}</p>
      </div>
    );
  }

  return (
    <div className={styles.page} data-testid="dashboard-page">
      <h1>Dashboard</h1>

      <div className={styles.statsGrid}>
        <StatCard label="Active Aircraft" value={stats?.active_aircraft ?? "—"} />
        <StatCard label="Flights Today" value={stats?.flights_today ?? "—"} />
        <StatCard
          label="Flights Last Hour"
          value={stats?.flights_in_last_hour ?? "—"}
        />
        <StatCard
          label="Ingest Rate"
          value={
            stats != null ? `${stats.ingest_rate_per_sec.toFixed(1)}/s` : "—"
          }
        />
        <StatCard
          label="Materializer Lag"
          value={
            stats?.materializer_lag_sec != null
              ? `${stats.materializer_lag_sec.toFixed(1)} s`
              : "—"
          }
        />
        <StatCard
          label="Storage Used"
          value={
            stats?.storage_bytes != null
              ? formatBytes(stats.storage_bytes)
              : "—"
          }
          sub={
            stats?.oldest_data_date != null
              ? `since ${stats.oldest_data_date}`
              : undefined
          }
        />
      </div>

      <section className={styles.section}>
        <h2>System Health</h2>
        <div className={styles.healthRow}>
          <StatusDot status={health?.postgres ?? "unknown"} />
          <span>PostgreSQL</span>
          <span className={styles.healthLabel}>{health?.postgres ?? "—"}</span>
          <span className={styles.healthSep} />
          <StatusDot status={health?.ultrafeeder ?? "unknown"} />
          <span>Ultrafeeder</span>
          <span className={styles.healthLabel}>{health?.ultrafeeder ?? "—"}</span>
          <span className={styles.healthSep} />
          <StatusDot status={health?.ingest_active ? "healthy" : "degraded"} />
          <span>Ingest</span>
          <span className={styles.healthLabel}>
            {health?.ingest_active ? "active" : "stale"}
          </span>
        </div>
      </section>

      <section className={styles.section}>
        <h2>Flights per Hour (24 h)</h2>
        <div className={styles.chartWrap}>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart
              data={hourly}
              margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
            >
              <XAxis
                dataKey="hour_start"
                tickFormatter={(v: string) =>
                  new Date(v).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                }
                tick={{ fill: "#aaa", fontSize: 11 }}
                interval="preserveStartEnd"
              />
              <YAxis
                allowDecimals={false}
                tick={{ fill: "#aaa", fontSize: 11 }}
                width={28}
              />
              <Tooltip
                contentStyle={{ background: "#1a1d27", border: "1px solid #333" }}
                labelFormatter={(v) =>
                  typeof v === "string" ? new Date(v).toLocaleString() : String(v)
                }
                formatter={(v) => [v, "flights"]}
              />
              <Bar dataKey="flight_count" fill="#3b82f6" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <div className={styles.twoCol}>
        <section className={styles.section}>
          <h2>Phase Distribution (1 h)</h2>
          <div className={styles.chartWrap}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={phases}
                layout="vertical"
                margin={{ top: 4, right: 8, bottom: 0, left: 56 }}
              >
                <XAxis
                  type="number"
                  tick={{ fill: "#aaa", fontSize: 11 }}
                  allowDecimals={false}
                />
                <YAxis
                  type="category"
                  dataKey="phase"
                  tick={{ fill: "#aaa", fontSize: 11 }}
                  width={56}
                />
                <Tooltip
                  contentStyle={{
                    background: "#1a1d27",
                    border: "1px solid #333",
                  }}
                  formatter={(v) => [v, "reports"]}
                />
                <Bar dataKey="count" radius={[0, 2, 2, 0]}>
                  {phases.map((entry) => (
                    <Cell
                      key={entry.phase}
                      fill={PHASE_COLORS[entry.phase] ?? "#7eb8f7"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {phases.length === 0 && (
            <p className={styles.empty}>No phase data in the last hour.</p>
          )}
        </section>

        <section className={styles.section}>
          <h2>Top Aircraft (24 h)</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>ICAO</th>
                  <th>Callsign</th>
                  <th>Flights</th>
                </tr>
              </thead>
              <tbody>
                {topAircraft.map((a) => (
                  <tr key={a.hex}>
                    <td className={styles.mono}>{a.hex.toUpperCase()}</td>
                    <td>{a.callsign ?? "—"}</td>
                    <td>{a.flight_count}</td>
                  </tr>
                ))}
                {topAircraft.length === 0 && (
                  <tr>
                    <td colSpan={3} className={styles.empty}>
                      No flights in the last 24 h.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
