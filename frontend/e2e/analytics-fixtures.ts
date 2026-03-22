import type {
  FlightSummary,
  TrackPoint,
  ApproachAnalysis,
  HeatmapSample,
  AirportSummary,
  RunwayUtilization,
  AirportHourlyPoint,
} from "../src/types/analytics";

export const SESSION_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
export const SESSION_ID_2 = "b2c3d4e5-f6a7-8901-bcde-f01234567891";
export const SESSION_ID_3 = "c3d4e5f6-a7b8-9012-cdef-012345678912";

export const FLIGHTS_LIST_FIXTURE: FlightSummary[] = [
  {
    session_id: SESSION_ID,
    hex: "a1b2c3",
    callsign: "UAL123",
    started_at: "2024-01-15T10:00:00Z",
    ended_at: "2024-01-15T11:30:00Z",
    on_ground: false,
    total_distance_nm: 142.5,
    departure_airport_icao: "KCMH",
    arrival_airport_icao: "KATL",
  },
  {
    session_id: SESSION_ID_2,
    hex: "b2c3d4",
    callsign: "DAL456",
    started_at: "2024-01-15T09:00:00Z",
    ended_at: "2024-01-15T10:45:00Z",
    on_ground: false,
    total_distance_nm: 98.3,
    departure_airport_icao: "KLCK",
    arrival_airport_icao: "KORD",
  },
  {
    session_id: SESSION_ID_3,
    hex: "c3d4e5",
    callsign: null,
    started_at: "2024-01-15T08:00:00Z",
    ended_at: null,
    on_ground: true,
    total_distance_nm: null,
    departure_airport_icao: null,
    arrival_airport_icao: null,
  },
];

export const TRACK_FIXTURE: TrackPoint[] = [
  { timestamp: "2024-01-15T10:00:00Z", lat: 39.998, lon: -82.998, alt_ft: 800, speed_kts: 120, vrate_fpm: 1500, track: 90, phase: "TOF" },
  { timestamp: "2024-01-15T10:02:00Z", lat: 40.010, lon: -82.950, alt_ft: 3500, speed_kts: 200, vrate_fpm: 2000, track: 91, phase: "CLB" },
  { timestamp: "2024-01-15T10:05:00Z", lat: 40.025, lon: -82.880, alt_ft: 8000, speed_kts: 250, vrate_fpm: 2500, track: 92, phase: "CLB" },
  { timestamp: "2024-01-15T10:10:00Z", lat: 40.040, lon: -82.800, alt_ft: 18000, speed_kts: 350, vrate_fpm: 1000, track: 93, phase: "CLB" },
  { timestamp: "2024-01-15T10:20:00Z", lat: 40.060, lon: -82.600, alt_ft: 35000, speed_kts: 450, vrate_fpm: 0, track: 94, phase: "CRZ" },
  { timestamp: "2024-01-15T10:50:00Z", lat: 39.900, lon: -82.300, alt_ft: 35000, speed_kts: 450, vrate_fpm: 0, track: 180, phase: "CRZ" },
  { timestamp: "2024-01-15T11:10:00Z", lat: 39.800, lon: -82.100, alt_ft: 20000, speed_kts: 350, vrate_fpm: -1500, track: 182, phase: "DES" },
  { timestamp: "2024-01-15T11:20:00Z", lat: 39.700, lon: -82.000, alt_ft: 8000, speed_kts: 280, vrate_fpm: -2000, track: 183, phase: "DES" },
  { timestamp: "2024-01-15T11:25:00Z", lat: 39.650, lon: -81.950, alt_ft: 3000, speed_kts: 180, vrate_fpm: -800, track: 184, phase: "APP" },
  { timestamp: "2024-01-15T11:29:00Z", lat: 39.620, lon: -81.930, alt_ft: 500, speed_kts: 140, vrate_fpm: -600, track: 184, phase: "LDG" },
];

export const APPROACH_ANALYSIS_FIXTURE: ApproachAnalysis = {
  runway: {
    icao: "KATL",
    designator: "26L",
    threshold_elevation_ft: 1026,
    heading_true: 261.5,
  },
  points: [
    { timestamp: "2024-01-15T11:20:00Z", distance_nm: 12.0, actual_alt_ft_msl: 5200, expected_alt_ft_msl: 4900, deviation_ft: 300, severity: "RED" },
    { timestamp: "2024-01-15T11:22:00Z", distance_nm: 9.0, actual_alt_ft_msl: 3800, expected_alt_ft_msl: 3700, deviation_ft: 100, severity: "GREEN" },
    { timestamp: "2024-01-15T11:24:00Z", distance_nm: 6.5, actual_alt_ft_msl: 2700, expected_alt_ft_msl: 2600, deviation_ft: 100, severity: "GREEN" },
    { timestamp: "2024-01-15T11:26:00Z", distance_nm: 4.0, actual_alt_ft_msl: 1900, expected_alt_ft_msl: 1700, deviation_ft: 200, severity: "YELLOW" },
    { timestamp: "2024-01-15T11:28:00Z", distance_nm: 1.5, actual_alt_ft_msl: 1200, expected_alt_ft_msl: 1100, deviation_ft: 100, severity: "GREEN" },
  ],
};

export const HEATMAP_SAMPLES_FIXTURE: HeatmapSample[] = Array.from({ length: 20 }, (_, i) => ({
  lat: 39.998 + (i - 10) * 0.01,
  lon: -82.998 + (i - 10) * 0.01,
  weight: 1.0,
}));

export const AIRPORT_SUMMARY_FIXTURE: AirportSummary[] = [
  { icao: "KCMH", name: "John Glenn Columbus International Airport", arrivals: 42, departures: 38 },
  { icao: "KLCK", name: "Rickenbacker International Airport", arrivals: 12, departures: 15 },
  { icao: "KOSU", name: "Ohio State University Airport", arrivals: 8, departures: 9 },
  { icao: "KTZR", name: "Bolton Field Airport", arrivals: 5, departures: 6 },
];

export const RUNWAY_UTILIZATION_FIXTURE: RunwayUtilization[] = [
  { airport_icao: "KCMH", designator: "28L", flight_count: 22 },
  { airport_icao: "KCMH", designator: "28R", flight_count: 18 },
  { airport_icao: "KLCK", designator: "23L", flight_count: 12 },
];

export const AIRPORT_HOURLY_FIXTURE_KCMH: AirportHourlyPoint[] = Array.from({ length: 25 }, (_, i) => ({
  hour_start: new Date(Date.now() - (24 - i) * 3600 * 1000).toISOString(),
  flight_count: Math.floor(Math.random() * 5),
}));

export const AIRPORT_HOURLY_FIXTURE_KLCK: AirportHourlyPoint[] = Array.from({ length: 25 }, (_, i) => ({
  hour_start: new Date(Date.now() - (24 - i) * 3600 * 1000).toISOString(),
  flight_count: Math.floor(Math.random() * 3),
}));
