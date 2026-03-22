import { create } from "zustand";
import type { Aircraft, AircraftMap, WsMessage } from "../types/aircraft";

interface AircraftState {
  aircraft: AircraftMap;
  lastTimestamp: number | null;
  connected: boolean;
  setConnected: (connected: boolean) => void;
  applyMessage: (msg: WsMessage) => void;
  clear: () => void;
}

export const useAircraftStore = create<AircraftState>((set) => ({
  aircraft: {},
  lastTimestamp: null,
  connected: false,

  setConnected: (connected) => set({ connected }),

  applyMessage: (msg) => {
    if (msg.type === "FULL_STATE") {
      set({ aircraft: msg.aircraft, lastTimestamp: msg.timestamp });
    } else if (msg.type === "DIFFERENTIAL_UPDATE") {
      set((state) => {
        const next: AircraftMap = { ...state.aircraft };
        // Apply updates (full records)
        for (const [hex, record] of Object.entries(msg.updates)) {
          next[hex] = record;
        }
        // Apply removals
        for (const hex of msg.removals) {
          delete next[hex];
        }
        return { aircraft: next, lastTimestamp: msg.timestamp };
      });
    }
  },

  clear: () => set({ aircraft: {}, lastTimestamp: null }),
}));

export type { Aircraft };
