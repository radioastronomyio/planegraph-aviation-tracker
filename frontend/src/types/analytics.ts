export interface TrackPoint {
  timestamp: string;
  lat: number;
  lon: number;
  alt_ft: number | null;
  speed_kts: number | null;
  vrate_fpm: number | null;
  track: number | null;
  phase: string | null;
}

export interface RunwayInfo {
  icao: string;
  designator: string;
  threshold_elevation_ft: number;
  heading_true: number;
}

export interface ApproachPoint {
  timestamp: string;
  distance_nm: number;
  actual_alt_ft_msl: number;
  expected_alt_ft_msl: number;
  deviation_ft: number;
  severity: "GREEN" | "YELLOW" | "RED";
}

export interface ApproachAnalysis {
  runway: RunwayInfo;
  points: ApproachPoint[];
}

export interface HeatmapSample {
  lat: number;
  lon: number;
  weight: number;
}

export interface FlightSummary {
  session_id: string;
  hex: string;
  callsign: string | null;
  started_at: string;
  ended_at: string | null;
  on_ground: boolean;
  total_distance_nm: number | null;
  departure_airport_icao: string | null;
  arrival_airport_icao: string | null;
}

export interface AirportSummary {
  icao: string;
  name: string;
  arrivals: number;
  departures: number;
}

export interface RunwayUtilization {
  airport_icao: string;
  designator: string;
  flight_count: number;
}

export interface AirportHourlyPoint {
  hour_start: string;
  flight_count: number;
}
