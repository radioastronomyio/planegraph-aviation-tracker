export const PHASE_COLORS: Record<string, string> = {
  GND: "#64748b",
  TOF: "#f59e0b",
  CLB: "#22c55e",
  CRZ: "#3b82f6",
  DES: "#a855f7",
  APP: "#f97316",
  LDG: "#ef4444",
  UNKNOWN: "#6b7280",
};

export const SEVERITY_COLORS: Record<string, string> = {
  GREEN: "#22c55e",
  YELLOW: "#f59e0b",
  RED: "#ef4444",
};

export function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
