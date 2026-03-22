import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { Deck } from "@deck.gl/core";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { HeatmapSample } from "../types/analytics";
import { fetchJson } from "../utils/api";
import { ensurePmtilesProtocol } from "../utils/pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";
import styles from "./HeatmapPage.module.css";

const INITIAL_VIEW = {
  longitude: -82.998,
  latitude: 39.998,
  zoom: 9,
  pitch: 0,
  bearing: 0,
};

const HOURS_OPTIONS = [1, 6, 12, 24, 48, 72, 168];

export function HeatmapPage() {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const deckCanvasRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckRef = useRef<Deck | null>(null);

  const [hours, setHours] = useState(24);
  const [samples, setSamples] = useState<HeatmapSample[]>([]);
  const [loading, setLoading] = useState(false);

  // Initialize map + deck once
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

  // Update heatmap layer when samples change
  useEffect(() => {
    if (!deckRef.current) return;

    const layer = new HeatmapLayer<HeatmapSample>({
      id: "heatmap",
      data: samples,
      getPosition: (d) => [d.lon, d.lat],
      getWeight: (d) => d.weight,
      radiusPixels: 30,
      intensity: 1,
      threshold: 0.05,
      colorRange: [
        [1, 152, 189],
        [73, 227, 206],
        [216, 254, 181],
        [254, 237, 177],
        [254, 173, 84],
        [209, 55, 78],
      ],
    });

    deckRef.current.setProps({ layers: [layer] });
  }, [samples]);

  // Fetch samples on mount and when hours changes
  useEffect(() => {
    setLoading(true);
    fetchJson<HeatmapSample[]>(`/api/v1/analytics/heatmap-samples?hours=${hours}&limit=50000`)
      .then((data) => setSamples(data))
      .catch(() => setSamples([]))
      .finally(() => setLoading(false));
  }, [hours]);

  return (
    <div className={styles.page} data-testid="heatmap-page">
      <div className={styles.controls} data-testid="heatmap-controls">
        <label className={styles.controlLabel}>Time window:</label>
        <select
          className={styles.select}
          value={hours}
          onChange={(e) => setHours(Number(e.target.value))}
          data-testid="hours-select"
        >
          {HOURS_OPTIONS.map((h) => (
            <option key={h} value={h}>
              {h < 24 ? `${h}h` : `${h / 24}d`}
            </option>
          ))}
        </select>
        <span className={styles.countBadge} data-testid="sample-count">
          {loading ? "Loading…" : `${samples.length.toLocaleString()} points`}
        </span>
      </div>

      <div className={styles.mapWrap}>
        <div ref={mapContainerRef} className={styles.map} />
        <canvas ref={deckCanvasRef} className={styles.deck} />
      </div>
    </div>
  );
}
