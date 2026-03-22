import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import type { FlightSummary } from "../types/analytics";
import { fetchJson } from "../utils/api";
import { formatDuration } from "../utils/format";
import styles from "./FlightsPage.module.css";

function buildUrl(filters: Filters, limit: number, offset: number): string {
  const params = new URLSearchParams();
  if (filters.callsign) params.set("callsign", filters.callsign);
  if (filters.hex) params.set("hex", filters.hex);
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  if (filters.min_duration_sec) params.set("min_duration_sec", String(filters.min_duration_sec));
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return `/api/v1/flights?${params.toString()}`;
}

interface Filters {
  callsign: string;
  hex: string;
  start: string;
  end: string;
  min_duration_sec: string;
}

const LIMIT = 50;

export function FlightsPage() {
  const [filters, setFilters] = useState<Filters>({ callsign: "", hex: "", start: "", end: "", min_duration_sec: "" });
  const [activeFilters, setActiveFilters] = useState<Filters>({ callsign: "", hex: "", start: "", end: "", min_duration_sec: "" });
  const [flights, setFlights] = useState<FlightSummary[]>([]);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchJson<FlightSummary[]>(buildUrl(activeFilters, LIMIT, page * LIMIT))
      .then((data) => setFlights(data))
      .catch((e: unknown) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [activeFilters, page]);

  function handleSearch() {
    setPage(0);
    setActiveFilters({ ...filters });
  }

  return (
    <div className={styles.page} data-testid="flights-page">
      <h1>Flights</h1>

      <div className={styles.filterBar}>
        <input
          className={styles.input}
          placeholder="Callsign prefix"
          value={filters.callsign}
          onChange={(e) => setFilters((f) => ({ ...f, callsign: e.target.value }))}
          data-testid="filter-callsign"
        />
        <input
          className={styles.input}
          placeholder="ICAO hex"
          value={filters.hex}
          onChange={(e) => setFilters((f) => ({ ...f, hex: e.target.value }))}
          data-testid="filter-hex"
        />
        <input
          className={styles.input}
          type="datetime-local"
          value={filters.start}
          onChange={(e) => setFilters((f) => ({ ...f, start: e.target.value }))}
          data-testid="filter-start"
        />
        <input
          className={styles.input}
          type="datetime-local"
          value={filters.end}
          onChange={(e) => setFilters((f) => ({ ...f, end: e.target.value }))}
          data-testid="filter-end"
        />
        <input
          className={styles.input}
          type="number"
          placeholder="Min duration (s)"
          value={filters.min_duration_sec}
          onChange={(e) => setFilters((f) => ({ ...f, min_duration_sec: e.target.value }))}
          data-testid="filter-min-duration"
        />
        <button className={styles.btn} onClick={handleSearch} data-testid="search-btn">
          Search
        </button>
      </div>

      {error && <p className={styles.errorMsg}>Error: {error}</p>}
      {loading && <p className={styles.loadingMsg}>Loading…</p>}

      <section className={styles.section}>
        <div className={styles.tableWrap}>
          <table className={styles.table} data-testid="flights-table">
            <thead>
              <tr>
                <th>Callsign</th>
                <th>Hex</th>
                <th>Started</th>
                <th>Duration</th>
                <th>Distance</th>
                <th>Dep</th>
                <th>Arr</th>
              </tr>
            </thead>
            <tbody>
              {flights.map((f) => (
                <tr key={f.session_id}>
                  <td>
                    <Link to={`/flights/${f.session_id}`} className={styles.link} data-testid="flight-row-link">
                      {f.callsign ?? "—"}
                    </Link>
                  </td>
                  <td className={styles.mono}>{f.hex.toUpperCase()}</td>
                  <td className={styles.mono}>{new Date(f.started_at).toLocaleString()}</td>
                  <td>{formatDuration(f.started_at, f.ended_at)}</td>
                  <td>{f.total_distance_nm != null ? `${f.total_distance_nm.toFixed(1)} nm` : "—"}</td>
                  <td className={styles.mono}>{f.departure_airport_icao ?? "—"}</td>
                  <td className={styles.mono}>{f.arrival_airport_icao ?? "—"}</td>
                </tr>
              ))}
              {!loading && flights.length === 0 && (
                <tr>
                  <td colSpan={7} className={styles.empty} data-testid="no-flights">
                    No flights found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className={styles.pagination}>
        <button
          className={styles.btn}
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={page === 0}
          data-testid="prev-btn"
        >
          ← Previous
        </button>
        <span className={styles.pageInfo} data-testid="page-info">Page {page + 1}</span>
        <button
          className={styles.btn}
          onClick={() => setPage((p) => p + 1)}
          disabled={flights.length < LIMIT}
          data-testid="next-btn"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
