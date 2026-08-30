"use client";

import { useEffect, useState } from "react";

type Event = { ts: string; kind: string; data: Record<string, unknown> };

const TONE: Record<string, string> = {
  signal: "var(--series-2)",
  order_open: "var(--series-1)",
  order_filled: "var(--good)",
  order_reprice: "var(--ink-secondary)",
  order_cancelled: "var(--ink-muted)",
  exit_signal: "var(--series-2)",
  order_close: "var(--series-1)",
  position_closed: "var(--ink-primary)",
  skip: "var(--ink-muted)",
  scan: "var(--ink-muted)",
  error: "var(--critical)",
};

/** Plain-English reasons, so a skip never reads as an unexplained silence. */
const WHY: Record<string, string> = {
  target_too_close: "its 3R target is too short a walk to pay for the option",
  over_budget: "one contract costs more than the position budget",
  illiquid: "its bid-ask is too wide a share of the premium to trade near mid",
  premium_implausible: "the quoted premium looks stale, not cheap",
  no_chain: "no two-sided market in the expiry window",
  no_greeks: "the chain came back without deltas",
  no_stop: "not enough history to freeze a pivot stop",
  stop_above_entry: "the pivot stop sits above entry",
  unfilled: "the limit order never filled inside the band",
};

function narrate(e: Event): string {
  const d = e.data as Record<string, string | number | boolean | null>;
  switch (e.kind) {
    case "scan":
      return `scanned ${d.symbols} symbols · ${d.open_positions} open of ${d.slots} slots · equity $${d.equity}`;
    case "signal":
      return `${d.symbol} crossed up at ${d.entry} — stop ${d.stop}, 3R target ${d.target} (${d.target_pct}% away)`;
    case "skip":
      return `passed on ${d.symbol}: ${WHY[String(d.reason)] ?? d.reason}${d.detail ? ` (${d.detail})` : ""}`;
    case "order_open":
      return `${d.dry_run ? "would buy" : "buying"} ${d.qty}× ${d.occ} at ${d.limit} — market ${d.bid}/${d.ask}, delta ${d.delta ?? "?"}`;
    case "order_reprice":
      return `not filling — moved the ${d.side} limit to ${d.to} (step ${d.step})`;
    case "order_filled":
      return `filled ${d.occ}${d.asked != null ? ` — asked ${d.asked}, got ${d.got}` : ""}`;
    case "order_cancelled":
      return `gave up on ${d.occ}: it would not fill inside the band`;
    case "exit_signal":
      return `${d.symbol} hit its ${d.reason === "stop" ? "stop" : d.reason === "target" ? "3R target" : "5-day expiry clock"} at ${d.underlying}`;
    case "order_close":
      return `closing ${d.qty}× ${d.occ} at ${d.limit} — market ${d.bid}/${d.ask}`;
    case "position_closed":
      return `closed ${d.symbol}: in at ${d.entry}, out at ${d.exit} — ${Number(d.pnl) >= 0 ? "+" : "−"}$${Math.abs(Number(d.pnl)).toFixed(2)}`;
    case "error":
      return `error: ${d.detail}`;
    default:
      return `${e.kind} ${JSON.stringify(d)}`;
  }
}

export default function BrainFeed() {
  const [events, setEvents] = useState<Event[] | null>(null);

  useEffect(() => {
    const load = () =>
      fetch("/api/events").then((r) => r.json()).then((d) => setEvents(d.events ?? [])).catch(() => {});
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="card p-5">
      <div className="eyebrow mb-3">bot decisions · live feed</div>
      {!events || events.length === 0 ? (
        <div className="py-6 text-center text-sm" style={{ color: "var(--ink-muted)" }}>
          Nothing logged yet — the feed fills on the bot&apos;s first pass.
        </div>
      ) : (
        <div className="max-h-96 overflow-y-auto font-mono2 text-[11px] space-y-1">
          {events.map((e, i) => (
            <div key={i} className="flex gap-3">
              <span className="shrink-0" style={{ color: "var(--ink-muted)" }}>
                {new Date(e.ts).toLocaleTimeString()}
              </span>
              <span style={{ color: TONE[e.kind] ?? "var(--ink-secondary)" }}>{narrate(e)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
