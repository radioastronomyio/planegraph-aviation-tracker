import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import { Deck } from "@deck.gl/core";
import { IconLayer } from "@deck.gl/layers";
import { useAircraftStore } from "../store/aircraftStore";
import type { Aircraft } from "../types/aircraft";
import "maplibre-gl/dist/maplibre-gl.css";
import styles from "./MapView.module.css";

// Columbus, OH center
const INITIAL_VIEW = {
  longitude: -82.998,
  latitude: 39.998,
  zoom: 9,
  pitch: 0,
  bearing: 0,
};

// PMTiles protocol registration (idempotent)
let pmtilesRegistered = false;
function ensurePmtilesProtocol() {
  if (pmtilesRegistered) return;
  const protocol = new Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);
  pmtilesRegistered = true;
}

const ATLAS_URL = "/atlas/aircraft-atlas.png";
const ATLAS_MAPPING_URL = "/atlas/aircraft-atlas.json";

interface IconData {
  hex: string;
  position: [number, number, number];
  angle: number;
  icon: string;
}

type IconMapping = Record<
  string,
  { x: number; y: number; width: number; height: number; anchorX?: number; anchorY?: number; mask?: boolean }
>;

function buildIconData(aircraft: Record<string, Aircraft>): IconData[] {
  return Object.values(aircraft).map((ac) => ({
    hex: ac.hex,
    position: [ac.lon, ac.lat, (ac.alt ?? 0) * 0.3048] as [number, number, number],
    angle: ac.track ?? 0,
    icon: ac.on_ground ? "ground" : (ac.category ?? "default"),
  }));
}

export function MapView() {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const deckCanvasRef = useRef<HTMLCanvasElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const deckRef = useRef<Deck | null>(null);
  const [atlasMapping, setAtlasMapping] = useState<IconMapping | null>(null);

  const aircraft = useAircraftStore((s) => s.aircraft);

  // Load atlas mapping JSON
  useEffect(() => {
    fetch(ATLAS_MAPPING_URL)
      .then((r) => r.json())
      .then((data: IconMapping) => setAtlasMapping(data))
      .catch(() => {
        setAtlasMapping({
          default: { x: 0, y: 0, width: 64, height: 64, anchorX: 32, anchorY: 32, mask: true },
        });
      });
  }, []);

  // Initialize map and deck
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
            attribution:
              "© <a href='https://www.openstreetmap.org/copyright'>OpenStreetMap</a> contributors",
          },
        },
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": "#1a1f2e" },
          },
          {
            id: "water",
            type: "fill",
            source: "columbus-tiles",
            "source-layer": "water",
            paint: { "fill-color": "#1c3a5e" },
          },
          {
            id: "landuse",
            type: "fill",
            source: "columbus-tiles",
            "source-layer": "landuse",
            paint: { "fill-color": "#1e2a1e", "fill-opacity": 0.5 },
          },
          {
            id: "roads",
            type: "line",
            source: "columbus-tiles",
            "source-layer": "transportation",
            paint: { "line-color": "#2d3a4a", "line-width": 1 },
          },
          {
            id: "admin-boundaries",
            type: "line",
            source: "columbus-tiles",
            "source-layer": "boundary",
            paint: { "line-color": "#3a4a5a", "line-width": 0.5 },
          },
        ],
      },
      center: [INITIAL_VIEW.longitude, INITIAL_VIEW.latitude],
      zoom: INITIAL_VIEW.zoom,
      // Pass options object instead of boolean to satisfy strict types
      attributionControl: { compact: false },
    });
    mapRef.current = map;

    // Create Deck.gl instance in overlaid mode
    const canvas = deckCanvasRef.current;
    const deck = new Deck({
      canvas,
      width: "100%",
      height: "100%",
      initialViewState: INITIAL_VIEW,
      controller: false, // MapLibre controls the view
      layers: [],
    });
    deckRef.current = deck;

    // Keep Deck viewport in sync with MapLibre
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

  // Update Deck.gl layers when aircraft data or atlas changes
  useEffect(() => {
    if (!deckRef.current || !atlasMapping) return;

    const data = buildIconData(aircraft);

    const layer = new IconLayer<IconData>({
      id: "aircraft",
      data,
      pickable: true,
      iconAtlas: ATLAS_URL,
      iconMapping: atlasMapping,
      getIcon: (d: IconData) => (d.icon in atlasMapping ? d.icon : "default"),
      getPosition: (d: IconData) => d.position,
      getAngle: (d: IconData) => -d.angle,
      getSize: 32,
      sizeScale: 1,
    });

    deckRef.current.setProps({ layers: [layer] });
  }, [aircraft, atlasMapping]);

  const count = Object.keys(aircraft).length;

  return (
    <div className={styles.wrapper} data-testid="map-view">
      <div ref={mapContainerRef} className={styles.map} data-testid="maplibre-map" />
      <canvas ref={deckCanvasRef} className={styles.deck} />
      <div className={styles.countBadge} data-testid="map-aircraft-count">
        {count} aircraft
      </div>
      <div className={styles.attribution} data-testid="osm-attribution">
        {"\u00a9"}{" "}
        <a
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noopener noreferrer"
        >
          OpenStreetMap
        </a>{" "}
        contributors
      </div>
    </div>
  );
}
