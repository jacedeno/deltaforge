"use client";

import { useEffect, useState } from "react";
import StatusStrip from "./StatusStrip";
import ThemeToggle from "./ThemeToggle";
import EquityChart from "./EquityChart";
import DailyPnl from "./DailyPnl";
import TradeHistory from "./TradeHistory";
import BrainFeed from "./BrainFeed";
import PayoffDiagram from "./PayoffDiagram";
import TradeChart from "./TradeChart";

type Position = {
  id: number; symbol: string; occ: string; strike: number; expiry: string; contracts: number;
  entryFill: number; limitPrice: number | null; debit: number | null; deltaAtEntry: number | null;
  signalTs: string; levels: { entry: number; stop: number; target: number };
  spot: number | null; bid: number | null; ask: number | null; mid: number | null;
  plAtMid: number | null; plPctOfDebit: number | null; breakeven: number; daysToExpiry: number;
};
type Snapshot = {
  asOf: string; journalReady: boolean;
  market: { isOpen: boolean };
  account: { number: string; equity: number; cash: number; optionsBuyingPower: number;
             inceptionEquity: number; pnlSinceInception: number };
  positions: Position[]; deployed: number; error?: string;
};

const money = (v: number) =>
  `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="card p-4">
      <div className="eyebrow mb-2">{label}</div>
      <div className="font-display text-2xl" style={{ color: tone ?? "var(--ink-primary)" }}>{value}</div>
      {sub && <div className="font-mono2 text-[11px] mt-1" style={{ color: "var(--ink-muted)" }}>{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    const load = () => fetch("/api/snapshot").then((r) => r.json()).then(setSnap).catch(() => {});
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, []);

  const acct = snap?.account;
  const since = acct ? acct.pnlSinceInception : 0;

  return (
    <>
      <StatusStrip marketOpen={snap?.market?.isOpen ?? null} />

      <main className="max-w-6xl mx-auto px-5 py-8 space-y-5">
        <header className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-3">
              <span className="font-display text-2xl" style={{ color: "var(--accent)" }}>Δ</span>
              <h1 className="font-display text-3xl">
                Delta<span style={{ color: "var(--accent)" }}>Forge</span>
              </h1>
            </div>
            <p className="text-sm mt-2 max-w-2xl" style={{ color: "var(--ink-secondary)" }}>
              Buys slightly in-the-money calls on the ML30 30-minute cross — 7–14 days out,
              around 0.55 delta — and exits on the underlying&apos;s own stop, its 3R target,
              or the five-day expiry clock. Alpaca paper.
            </p>
          </div>
          <ThemeToggle />
        </header>

        {snap?.error && (
          <div className="card p-4 font-mono2 text-[12px]" style={{ color: "var(--critical)" }}>
            {snap.error}
          </div>
        )}

        <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Tile
            label="equity"
            value={acct ? money(acct.equity) : "—"}
            sub={acct ? `${since >= 0 ? "+" : "−"}$${Math.abs(since).toFixed(2)} since inception` : undefined}
            tone={since >= 0 ? "var(--delta-up)" : "var(--delta-down)"}
          />
          <Tile
            label="open positions"
            value={snap ? String(snap.positions.length) : "—"}
            sub={acct ? `of ${Math.min(15, Math.floor(acct.equity / 300))} slots` : undefined}
          />
          <Tile
            label="capital deployed"
            value={snap ? money(snap.deployed) : "—"}
            sub={acct && acct.equity ? `${((snap!.deployed / acct.equity) * 100).toFixed(0)}% of equity` : undefined}
          />
          <Tile label="cash" value={acct ? money(acct.cash) : "—"} />
        </section>

        <EquityChart />

        <section className="card p-5">
          <div className="eyebrow mb-4">open positions</div>
          {!snap || snap.positions.length === 0 ? (
            <div className="py-8 text-center text-sm" style={{ color: "var(--ink-muted)" }}>
              No open positions — the bot is waiting for a signal whose 3R target is far
              enough away to be worth an option.
            </div>
          ) : (
            <div className="space-y-3">
              {snap.positions.map((p) => {
                const isOpen = expanded === p.id;
                const up = (p.plAtMid ?? 0) >= 0;
                return (
                  <div key={p.id} className="rounded-lg" style={{ background: "var(--surface-2)" }}>
                    <button onClick={() => setExpanded(isOpen ? null : p.id)}
                            className="w-full p-4 flex items-center gap-4 text-left">
                      <div className="w-20">
                        <div className="font-display font-semibold">{p.symbol}</div>
                        <div className="font-mono2 text-[10px]" style={{ color: "var(--ink-muted)" }}>
                          {p.daysToExpiry}d left
                        </div>
                      </div>
                      <div className="flex-1 font-mono2 text-[11px]" style={{ color: "var(--ink-secondary)" }}>
                        {p.strike}c ×{p.contracts} · in at {p.entryFill.toFixed(2)}
                        {p.bid != null && ` · now ${p.bid.toFixed(2)}/${p.ask?.toFixed(2)}`}
                      </div>
                      <div className="text-right">
                        <div className="font-mono2 text-sm" style={{ color: up ? "var(--delta-up)" : "var(--delta-down)" }}>
                          {p.plAtMid == null ? "—" : money(p.plAtMid)}
                        </div>
                        <div className="font-mono2 text-[10px]" style={{ color: "var(--ink-muted)" }}>
                          {p.plPctOfDebit == null ? "" : `${p.plPctOfDebit.toFixed(0)}% of debit`}
                        </div>
                      </div>
                      <PayoffDiagram strike={p.strike} premium={p.entryFill} spot={p.spot}
                                     stop={p.levels.stop} target={p.levels.target}
                                     width={160} height={56} compact />
                      <span style={{ color: "var(--ink-muted)" }}>{isOpen ? "▾" : "▸"}</span>
                    </button>
                    {isOpen && (
                      <div className="px-4 pb-4">
                        <TradeChart symbol={p.symbol} signalTs={p.signalTs} entry={p.levels.entry}
                                    stop={p.levels.stop} target={p.levels.target} />
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4 font-mono2 text-[11px]"
                             style={{ color: "var(--ink-secondary)" }}>
                          <div><div className="eyebrow mb-1">breakeven</div>{p.breakeven.toFixed(2)}</div>
                          <div><div className="eyebrow mb-1">asked / filled</div>
                               {p.limitPrice?.toFixed(2) ?? "—"} / {p.entryFill.toFixed(2)}</div>
                          <div><div className="eyebrow mb-1">delta at entry</div>{p.deltaAtEntry?.toFixed(3) ?? "—"}</div>
                          <div><div className="eyebrow mb-1">max loss</div>{money(p.debit ?? 0)}</div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <div className="grid lg:grid-cols-2 gap-5">
          <DailyPnl />
          <div className="card p-5">
            <div className="eyebrow mb-3">how it works</div>
            <ol className="space-y-3 text-sm" style={{ color: "var(--ink-secondary)" }}>
              <li><span className="font-mono2 text-[11px]" style={{ color: "var(--accent)" }}>01 · SIGNAL</span><br />
                ML30 fresh cross on 30-minute bars across 45 liquid names under $150.</li>
              <li><span className="font-mono2 text-[11px]" style={{ color: "var(--accent)" }}>02 · FILTER</span><br />
                Only if the 3R target sits 5%+ away — nearer than that, the option cannot
                pay for its own spread and theta.</li>
              <li><span className="font-mono2 text-[11px]" style={{ color: "var(--accent)" }}>03 · STRUCTURE</span><br />
                One call near 0.55 delta, 7–14 DTE, $300 a position, limit at mid.</li>
              <li><span className="font-mono2 text-[11px]" style={{ color: "var(--accent)" }}>04 · MANAGE</span><br />
                Exit on the underlying&apos;s stop, its 3R target, or five days to expiry —
                first touch wins, stop before target.</li>
            </ol>
          </div>
        </div>

        <TradeHistory />
        <BrainFeed />

        <footer className="pt-4 pb-8 text-center font-mono2 text-[11px] space-y-1"
                style={{ color: "var(--ink-muted)" }}>
          <div>paper account · refreshes every 15s · not financial advice</div>
          <div>Crafted by Jose Cedeño. Built on bare metal.</div>
        </footer>
      </main>
    </>
  );
}
