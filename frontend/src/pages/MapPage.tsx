import { useAircraftWebSocket } from "../hooks/useAircraftWebSocket";
import { MapView } from "../components/MapView";

export function MapPage() {
  useAircraftWebSocket();
  return <MapView />;
}
