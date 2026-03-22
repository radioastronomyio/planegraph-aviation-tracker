import { useEffect, useRef } from "react";
import { useAircraftStore } from "../store/aircraftStore";
import type { WsMessage } from "../types/aircraft";

const WS_URL =
  (import.meta.env.VITE_WS_URL as string | undefined) ??
  `ws://${window.location.host}/api/ws/live`;

const RECONNECT_DELAY_MS = 3000;

export function useAircraftWebSocket(): void {
  const applyMessage = useAircraftStore((s) => s.applyMessage);
  const setConnected = useAircraftStore((s) => s.setConnected);
  const clear = useAircraftStore((s) => s.clear);

  const wsRef = useRef<WebSocket | null>(null);
  const unmountedRef = useRef(false);

  useEffect(() => {
    unmountedRef.current = false;

    function connect() {
      if (unmountedRef.current) return;

      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as WsMessage;
          applyMessage(msg);
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        setConnected(false);
        clear();
        if (!unmountedRef.current) {
          setTimeout(connect, RECONNECT_DELAY_MS);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      unmountedRef.current = true;
      wsRef.current?.close();
      setConnected(false);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
}
