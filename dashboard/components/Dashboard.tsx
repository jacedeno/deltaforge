"use client";

import { useEffect, useState } from "react";
import StatusStrip from "./StatusStrip";
import ThemeToggle from "./ThemeToggle";
import EquityChart from "./EquityChart";
import DailyPnl from "./DailyPnl";
import TradeHistory from "./TradeHistory";
import BrainFeed from "./BrainFeed";
import PayoffDiagram from "./PayoffDiagram";
import Logo from "./Logo";
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
            <div className="flex items-center gap-3">
              <Logo size={40} />
              <h1 className="font-display text-3xl">
                Delta<span style={{ color: "var(--accent)" }}>Forge</span>
              </h1>
            </div>
            <p className="text-sm mt-2 max-w-2xl" style={{ color: "var(--ink-secondary)" }}>
              Buys slightly in-the-money calls on the ML30 30-minute cross — 7–14 days out,
              around 0.55 delta — and exits on the underlying&apos;s own stop, its 3R target,
              or the five-day expiry clock. Alpaca paper.
            </p>
            {/* The marks carry this, so they are sized to be read rather than
                noticed: 40px, the same as the DeltaForge logo above them, on
                their own panel so the header reads title → what it does →
                who it was built for. */}
            <div
              className="inline-flex flex-wrap items-center gap-x-5 gap-y-3 mt-4 px-4 py-3 rounded-lg"
              style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
            >
              <span className="eyebrow">built for</span>
              <a
                href="https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon"
                target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2.5 transition-opacity hover:opacity-75"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/alpaca.png" width={40} height={40} alt="Alpaca" className="rounded-md"
                     style={{ border: "1px solid var(--border)" }} />
                <span className="text-[13px] leading-tight" style={{ color: "var(--ink-primary)" }}>
                  Alpaca<br />
                  <span className="font-mono2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
                    AI Trading Agents Hackathon
                  </span>
                </span>
              </a>
              <a
                href="https://lablab.ai" target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2.5 transition-opacity hover:opacity-75"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/lablab.svg" width={40} height={40} alt="lablab.ai" className="rounded-md"
                     style={{ border: "1px solid var(--border)" }} />
                <span className="text-[13px] leading-tight" style={{ color: "var(--ink-primary)" }}>
                  lablab.ai<br />
                  <span className="font-mono2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
                    hackathon host
                  </span>
                </span>
              </a>
            </div>
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
            sub={acct ? `of ${Math.min(14, Math.floor(acct.equity / 7000))} slots` : undefined}
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
                      {/* The whole row toggles, but a lone muted glyph told
                          nobody that — this chip is the visible handle. */}
                      <span className="font-mono2 text-[11px] px-2.5 py-1.5 rounded-md flex-none"
                            style={{
                              background: isOpen ? "var(--accent)" : "var(--surface-1)",
                              color: isOpen ? "var(--page)" : "var(--ink-secondary)",
                              border: "1px solid var(--border)",
                            }}>
                        {isOpen ? "▾ close" : "▸ chart"}
                      </span>
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

        <footer className="pt-6 pb-10 font-mono2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap gap-2">
              {["Alpaca Options API", "ML30 30m signal", "Paper Trading", "Bare metal"].map((t) => (
                <span key={t} className="rounded-full border px-3 py-1"
                      style={{ borderColor: "var(--grid)" }}>
                  {t}
                </span>
              ))}
            </div>
            <div className="text-right">
              {acct ? `account ${acct.number} · ` : ""}refreshes every 15s · not financial advice
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t pt-4"
               style={{ borderColor: "var(--grid)" }}>
            <div>
              <a href="https://geekendzone.com" target="_blank" rel="noopener noreferrer"
                 className="font-display text-sm font-semibold underline-offset-2 hover:underline"
                 style={{ color: "var(--accent)" }}>
                GeekendZone
              </a>
              <p className="mt-0.5">Crafted by Jose Cedeño. Built on bare metal.</p>
            </div>
            <nav className="flex flex-wrap items-center gap-4" aria-label="Elsewhere">
              {[
                {
                  href: "https://linkedin.com/in/joseangelcedeno", label: "LinkedIn",
                  d: "M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.83-2.05 3.77-2.05 4.03 0 4.78 2.65 4.78 6.1V21h-4v-5.4c0-1.29-.02-2.95-1.8-2.95-1.8 0-2.08 1.4-2.08 2.85V21H9z",
                },
                {
                  href: "https://github.com/jacedeno", label: "GitHub",
                  d: "M12 .5C5.73.5.5 5.73.5 12a11.5 11.5 0 0 0 7.86 10.92c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.54-3.88-1.54-.53-1.34-1.29-1.7-1.29-1.7-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.2 1.77 1.2 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.56-.29-5.25-1.28-5.25-5.7 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.8 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.12 3.05.74.81 1.18 1.84 1.18 3.1 0 4.43-2.69 5.4-5.26 5.69.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 23.5 12C23.5 5.73 18.27.5 12 .5z",
                },
                {
                  href: "mailto:jacedeno@geekendzone.com", label: "Email",
                  d: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4.24-8 4.62-8-4.62V6l8 4.62L20 6z",
                },
              ].map((l) => (
                <a key={l.label} href={l.href}
                   {...(l.href.startsWith("http")
                     ? { target: "_blank", rel: "noopener noreferrer" } : {})}
                   className="flex items-center gap-1.5 transition-colors"
                   style={{ color: "var(--ink-secondary)" }}
                   onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent)")}
                   onMouseLeave={(e) => (e.currentTarget.style.color = "var(--ink-secondary)")}>
                  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="h-3.5 w-3.5">
                    <path d={l.d} />
                  </svg>
                  {l.label}
                </a>
              ))}
              <a href="https://geekendzone.com" target="_blank" rel="noopener noreferrer"
                 className="font-mono2 underline-offset-2 hover:underline"
                 style={{ color: "var(--ink-secondary)" }}>
                geekendzone.com
              </a>
            </nav>
          </div>
        </footer>
      </main>
    </>
  );
}
