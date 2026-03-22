import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { Deck } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { TrackPoint } from "../types/analytics";
import { PHASE_COLORS, hexToRgb } from "../utils/colors";
import { ensurePmtilesProtocol } from "../utils/pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";
import styles from "./FlightMap.module.css";

const INITIAL_VIEW = {
  longitude: -82.998,
  latitude: 39.998,
  zoom: 9,
  pitch: 0,
  bearing: 0,
};

export interface FlightMapProps {
  trackPoints: TrackPoint[];
  focusIndex: number | null;
  /** Extra scatter points to render (e.g. approach severity dots) */
  extraScatterData?: Array<{ position: [number, number]; color: [number, number, number]; radius?: number }>;
  /** Single marker for runway threshold */
  thresholdPoint?: { lat: number; lon: number } | null;
}

export function FlightMap({ trackPoints, focusIndex, extraScatterData, thresholdPoint }: FlightMapProps) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const deckCanvasRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckRef = useRef<Deck | null>(null);

  // Initialize map and deck once
  useEffect(() => {
    if (!mapContainerRef.current || !deckCanvasRef.current) return;

    ensurePmtilesProtocol();

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
        sources: {
          "columbus-tiles": {
            type: "vector",
            url: "pmtiles:///tiles/columbus-region.pmtiles",
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [
          { id: "background", type: "background", paint: { "background-color": "#1a1f2e" } },
          { id: "water", type: "fill", source: "columbus-tiles", "source-layer": "water", paint: { "fill-color": "#1c3a5e" } },
          { id: "landuse", type: "fill", source: "columbus-tiles", "source-layer": "landuse", paint: { "fill-color": "#1e2a1e", "fill-opacity": 0.5 } },
          { id: "roads", type: "line", source: "columbus-tiles", "source-layer": "transportation", paint: { "line-color": "#2d3a4a", "line-width": 1 } },
          { id: "admin-boundaries", type: "line", source: "columbus-tiles", "source-layer": "boundary", paint: { "line-color": "#3a4a5a", "line-width": 0.5 } },
        ],
      },
      center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
      zoom: INITIAL_VIEW.zoom,
      attributionControl: { compact: false },
    });
    mapRef.current = map;

    const deck = new Deck({
      canvas: deckCanvasRef.current,
      width: "100%",
      height: "100%",
      initialViewState: INITIAL_VIEW,
      controller: false,
      layers: [],
    });
    deckRef.current = deck;

    function syncDeck() {
      if (!mapRef.current || !deckRef.current) return;
      const center = map.getCenter();
      deckRef.current.setProps({
        viewState: {
          longitude: center.lng,
          latitude: center.lat,
          zoom: map.getZoom(),
          bearing: map.getBearing(),
          pitch: map.getPitch(),
        },
      });
    }

    map.on("move", syncDeck);
    map.on("zoom", syncDeck);
    map.on("rotate", syncDeck);
    map.on("pitch", syncDeck);

    return () => {
      deck.finalize();
      map.remove();
      mapRef.current = null;
      deckRef.current = null;
    };
  }, []);

  // Update layers when data or focusIndex changes
  useEffect(() => {
    if (!deckRef.current) return;

    const layers = [];

    // Path layer colored by phase
    if (trackPoints.length > 1) {
      // Merge consecutive same-phase points into segments
      const segments: Array<{ path: [number, number][]; color: [number, number, number] }> = [];
      let current: [number, number][] = [[trackPoints[0].lon, trackPoints[0].lat]];
      let currentPhase = trackPoints[0].phase ?? "UNKNOWN";

      for (let i = 1; i < trackPoints.length; i++) {
        const pt = trackPoints[i];
        const phase = pt.phase ?? "UNKNOWN";
        current.push([pt.lon, pt.lat]);
        if (phase !== currentPhase || i === trackPoints.length - 1) {
          segments.push({
            path: [...current],
            color: hexToRgb(PHASE_COLORS[currentPhase] ?? "#7eb8f7"),
          });
          current = [[pt.lon, pt.lat]];
          currentPhase = phase;
        }
      }

      layers.push(
        new PathLayer({
          id: "trajectory",
          data: segments,
          getPath: (d) => d.path,
          getColor: (d) => d.color,
          getWidth: 3,
          widthMinPixels: 2,
        })
      );
    }

    // Extra scatter (approach severity dots)
    if (extraScatterData && extraScatterData.length > 0) {
      layers.push(
        new ScatterplotLayer({
          id: "approach-dots",
          data: extraScatterData,
          getPosition: (d) => d.position,
          getColor: (d) => d.color,
          getRadius: (d) => d.radius ?? 6,
          radiusMinPixels: 4,
        })
      );
    }

    // Runway threshold marker
    if (thresholdPoint) {
      layers.push(
        new ScatterplotLayer({
          id: "threshold",
          data: [{ position: [thresholdPoint.lon, thresholdPoint.lat] as [number, number] }],
          getPosition: (d) => d.position,
          getColor: () => [126, 184, 247] as [number, number, number],
          getRadius: 12,
          radiusMinPixels: 8,
        })
      );
    }

    // Replay marker
    if (focusIndex !== null && trackPoints[focusIndex]) {
      const pt = trackPoints[focusIndex];
      layers.push(
        new ScatterplotLayer({
          id: "replay-marker",
          data: [{ position: [pt.lon, pt.lat] as [number, number] }],
          getPosition: (d) => d.position,
          getColor: () => [245, 158, 11] as [number, number, number],
          getRadius: 8,
          radiusMinPixels: 6,
          stroked: true,
          lineWidthMinPixels: 2,
          getFillColor: () => [245, 158, 11],
          getLineColor: () => [255, 255, 255] as [number, number, number],
        })
      );
    }

    deckRef.current.setProps({ layers });
  }, [trackPoints, focusIndex, extraScatterData, thresholdPoint]);

  // Fit bounds to track on load
  useEffect(() => {
    if (trackPoints.length === 0 || !mapRef.current) return;

    const lats = trackPoints.map((p) => p.lat);
    const lons = trackPoints.map((p) => p.lon);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    const tryFit = () => {
      if (!mapRef.current) return;
      mapRef.current.fitBounds(
        [[minLon, minLat], [maxLon, maxLat]],
        { padding: 40, maxZoom: 13 }
      );
    };

    if (mapRef.current.loaded()) {
      tryFit();
    } else {
      mapRef.current.once("load", tryFit);
    }
  }, [trackPoints]);

  return (
    <div className={styles.wrapper} data-testid="flight-map">
      <div ref={mapContainerRef} className={styles.map} />
      <canvas ref={deckCanvasRef} className={styles.deck} />
      {focusIndex !== null && (
        <div className={styles.markerLabel} data-testid="replay-marker">
          {trackPoints[focusIndex] && (
            <>
              {trackPoints[focusIndex].alt_ft != null && `${trackPoints[focusIndex].alt_ft} ft`}
              {trackPoints[focusIndex].speed_kts != null && ` · ${trackPoints[focusIndex].speed_kts} kts`}
            </>
          )}
        </div>
      )}
    </div>
  );
}
