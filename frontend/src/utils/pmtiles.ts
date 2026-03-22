import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";

let registered = false;

export function ensurePmtilesProtocol(): void {
  if (registered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  registered = true;
}
