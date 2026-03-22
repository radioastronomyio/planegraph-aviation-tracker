export interface Aircraft {
  hex: string;
  session_id: string;
  callsign: string | null;
  lat: number;
  lon: number;
  alt: number | null;
  track: number | null;
  speed: number | null;
  vrate: number | null;
  phase: string | null;
  squawk: string | null;
  on_ground: boolean;
  category: string | null;
  last_seen: string;
}

export type AircraftMap = Record<string, Aircraft>;

export interface FullStateMessage {
  type: "FULL_STATE";
  timestamp: number;
  aircraft: AircraftMap;
}

export interface DifferentialUpdateMessage {
  type: "DIFFERENTIAL_UPDATE";
  timestamp: number;
  updates: AircraftMap;
  removals: string[];
}

export type WsMessage = FullStateMessage | DifferentialUpdateMessage;
