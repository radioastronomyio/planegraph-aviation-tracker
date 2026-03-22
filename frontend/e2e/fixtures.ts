import type { FullStateMessage, DifferentialUpdateMessage } from "../src/types/aircraft";

export const FULL_STATE_FIXTURE: FullStateMessage = {
  type: "FULL_STATE",
  timestamp: 1742567400.0,
  aircraft: {
    a12345: {
      hex: "a12345",
      session_id: "550e8400-e29b-41d4-a716-446655440000",
      callsign: "SWA2007",
      lat: 39.96,
      lon: -83.0,
      alt: 6400,
      track: 270.0,
      speed: 250,
      vrate: -1200,
      phase: "APP",
      squawk: "1234",
      on_ground: false,
      category: "A3",
      last_seen: "2026-03-21T14:30:00Z",
    },
    b56789: {
      hex: "b56789",
      session_id: "660e8400-e29b-41d4-a716-446655440001",
      callsign: "DAL1501",
      lat: 40.05,
      lon: -82.88,
      alt: 12500,
      track: 90.0,
      speed: 320,
      vrate: 1800,
      phase: "CLB",
      squawk: "4521",
      on_ground: false,
      category: "A3",
      last_seen: "2026-03-21T14:30:01Z",
    },
  },
};

export const DIFFERENTIAL_UPDATE_FIXTURE: DifferentialUpdateMessage = {
  type: "DIFFERENTIAL_UPDATE",
  timestamp: 1742567401.0,
  updates: {
    a12345: {
      hex: "a12345",
      session_id: "550e8400-e29b-41d4-a716-446655440000",
      callsign: "SWA2007",
      lat: 39.955,
      lon: -83.01,
      alt: 6200,
      track: 271.0,
      speed: 245,
      vrate: -1300,
      phase: "APP",
      squawk: "1234",
      on_ground: false,
      category: "A3",
      last_seen: "2026-03-21T14:30:01Z",
    },
  },
  removals: ["b56789"],
};

export const DIFFERENTIAL_ADD_FIXTURE: DifferentialUpdateMessage = {
  type: "DIFFERENTIAL_UPDATE",
  timestamp: 1742567402.0,
  updates: {
    c99999: {
      hex: "c99999",
      session_id: "770e8400-e29b-41d4-a716-446655440002",
      callsign: "UAL400",
      lat: 39.9,
      lon: -83.1,
      alt: 3000,
      track: 180.0,
      speed: 200,
      vrate: -800,
      phase: "APP",
      squawk: "7700",
      on_ground: false,
      category: "A4",
      last_seen: "2026-03-21T14:30:02Z",
    },
  },
  removals: [],
};
