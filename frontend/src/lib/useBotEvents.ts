"use client";

import { useEffect, useState } from "react";
import { getToken, sseUrl } from "@/lib/api";

export function useBotEvents() {
  const [lastEvent, setLastEvent] = useState<Record<string, unknown> | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    // EventSource no soporta headers; usamos fetch stream fallback simple via poll heartbeat endpoint
    // Para SSE autenticado: polyfill con fetch ReadableStream
    const ac = new AbortController();
    let alive = true;

    async function connect() {
      try {
        const res = await fetch(sseUrl(), {
          headers: { Authorization: `Bearer ${token}` },
          signal: ac.signal,
        });
        if (!res.ok || !res.body) {
          setConnected(false);
          return;
        }
        setConnected(true);
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (alive) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() || "";
          for (const part of parts) {
            const line = part.split("\n").find((l) => l.startsWith("data: "));
            if (!line) continue;
            try {
              setLastEvent(JSON.parse(line.slice(6)));
            } catch {
              /* ignore */
            }
          }
        }
      } catch {
        if (alive) setConnected(false);
      }
    }
    connect();
    return () => {
      alive = false;
      ac.abort();
    };
  }, []);

  return { lastEvent, connected };
}
