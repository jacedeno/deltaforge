"use client";

import { useEffect, useState } from "react";

type Health = {
  alive: boolean;
  degraded: boolean;
  ageSeconds?: number;
  failures?: number;
  lastScan?: string | null;
  uptimeSeconds?: number;
  note?: string;
};

function hhmm(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function StatusStrip({ marketOpen }: { marketOpen: boolean | null }) {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    const load = () =>
      fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => {});
    load();
    const id = setInterval(load, 20_000);
    return () => clearInterval(id);
  }, []);

  const state = !health
    ? { label: "…", color: "var(--ink-muted)" }
    : health.degraded
      ? { label: `BOT DEGRADED (${health.failures} failed passes)`, color: "var(--critical)" }
      : health.alive
        ? { label: "BOT LIVE", color: "var(--good)" }
        : { label: "BOT DOWN", color: "var(--critical)" };

  return (
    <div
      className="w-full border-b"
      style={{ background: "var(--surface-2)", borderColor: "var(--border)" }}
    >
      <div className="max-w-6xl mx-auto px-5 py-2 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono2 text-[11px]"
        style={{ color: "var(--ink-secondary)" }}>
        <span className="flex items-center gap-2">
          <span
            className={`inline-block w-2 h-2 rounded-full ${health?.alive ? "live-dot" : ""}`}
            style={{ background: state.color }}
          />
          <span style={{ color: state.color }}>{state.label}</span>
        </span>
        <span>market {marketOpen == null ? "…" : marketOpen ? "OPEN" : "CLOSED"}</span>
        {health?.lastScan && (
          <span>last scan {new Date(health.lastScan).toLocaleTimeString()}</span>
        )}
        {health?.ageSeconds != null && <span>heartbeat {health.ageSeconds}s ago</span>}
        {health?.uptimeSeconds ? <span>uptime {hhmm(health.uptimeSeconds)}</span> : null}
        {health?.note ? <span style={{ color: "var(--ink-muted)" }}>{health.note}</span> : null}
      </div>
    </div>
  );
}
