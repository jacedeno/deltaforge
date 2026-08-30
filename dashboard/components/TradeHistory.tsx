"use client";

import { useEffect, useState } from "react";
import TradeChart from "./TradeChart";
import PayoffDiagram from "./PayoffDiagram";

type Trade = {
  id: number; status: string; symbol: string; occ: string; strike: number; expiry: string;
  dte_at_entry: number; delta_at_entry: number | null; signal_ts: string; entry_price: number;
  stop_price: number; target_price: number; contracts: number; limit_price: number | null;
  entry_fill: number | null; entry_ts: string | null; debit: number | null; fees: number;
  exit_ts: string | null; exit_limit: number | null; exit_fill: number | null;
  exit_reason: string | null; underlying_at_exit: number | null; pnl: number | null;
};
type Fill = { order_id: string; side: string; qty: number; price: number; filled_at: string; leg: string };
type Stats = {
  closed: number; open: number; aborted: number; totalPnl: number; winRate: number;
  profitFactor: number; avgWin: number; avgLoss: number; avgSlippage: number | null;
};

const money = (v: number) => `${v < 0 ? "−" : ""}$${Math.abs(v).toFixed(2)}`;

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="eyebrow mb-1">{label}</div>
      <div className="font-mono2 text-sm" style={{ color: tone ?? "var(--ink-primary)" }}>{value}</div>
    </div>
  );
}

export default function TradeHistory() {
  const [data, setData] = useState<{ trades: Trade[]; fills: Record<number, Fill[]>; stats: Stats | null; note?: string } | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    const load = () => fetch("/api/trades").then((r) => r.json()).then(setData).catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const closed = (data?.trades ?? []).filter((t) => t.status === "closed");
  const s = data?.stats;

  return (
    <div className="card p-5">
      <div className="eyebrow mb-4">trade history</div>

      {s && s.closed > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-5 pb-5 border-b"
             style={{ borderColor: "var(--border)" }}>
          <Stat label="net p&l" value={money(s.totalPnl)}
                tone={s.totalPnl >= 0 ? "var(--delta-up)" : "var(--delta-down)"} />
          <Stat label="win rate" value={`${(s.winRate * 100).toFixed(0)}%`} />
          <Stat label="profit factor" value={Number.isFinite(s.profitFactor) ? s.profitFactor.toFixed(2) : "∞"} />
          <Stat label="avg win" value={money(s.avgWin)} />
          <Stat label="avg loss" value={money(s.avgLoss)} />
          {/* Cents paid above the bot's own limit — the backtest's load-bearing guess, measured. */}
          <Stat
            label="avg slippage"
            value={s.avgSlippage == null ? "—" : `${s.avgSlippage >= 0 ? "+" : "−"}$${Math.abs(s.avgSlippage).toFixed(3)}`}
            tone={s.avgSlippage != null && s.avgSlippage > 0.02 ? "var(--critical)" : undefined}
          />
        </div>
      )}

      {closed.length === 0 ? (
        <div className="py-8 text-center text-sm" style={{ color: "var(--ink-muted)" }}>
          {data?.note ?? "No closed trades yet — the first ones appear as positions are exited."}
        </div>
      ) : (
        <div className="divide-y" style={{ borderColor: "var(--border)" }}>
          {closed.map((t) => {
            const win = (t.pnl ?? 0) > 0;
            const isOpen = expanded === t.id;
            return (
              <div key={t.id} style={{ borderColor: "var(--border)" }} className="border-t first:border-t-0">
                <button
                  onClick={() => setExpanded(isOpen ? null : t.id)}
                  className="w-full py-3 flex items-center gap-3 text-left"
                >
                  <span className="font-mono2 text-[11px] w-20" style={{ color: "var(--ink-muted)" }}>
                    {t.exit_ts ? new Date(t.exit_ts).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—"}
                  </span>
                  <span className="font-display font-semibold w-16">{t.symbol}</span>
                  <span className="font-mono2 text-[11px] flex-1" style={{ color: "var(--ink-secondary)" }}>
                    {t.strike}c ×{t.contracts} · {t.dte_at_entry}d
                  </span>
                  <span
                    className="font-mono2 text-[10px] px-2 py-0.5 rounded"
                    style={{
                      background: win ? "color-mix(in srgb, var(--good) 18%, transparent)" : "color-mix(in srgb, var(--critical) 18%, transparent)",
                      color: win ? "var(--delta-up)" : "var(--delta-down)",
                    }}
                  >
                    {(t.exit_reason ?? "").toUpperCase()}
                  </span>
                  <span className="font-mono2 text-sm w-24 text-right"
                        style={{ color: win ? "var(--delta-up)" : "var(--delta-down)" }}>
                    {money(t.pnl ?? 0)}
                  </span>
                  <span className="w-20 text-right font-mono2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
                    {t.debit ? `${(((t.pnl ?? 0) / t.debit) * 100).toFixed(0)}%` : ""}
                  </span>
                  <span style={{ color: "var(--ink-muted)" }}>{isOpen ? "▾" : "▸"}</span>
                </button>

                {isOpen && (
                  <div className="pb-5 grid lg:grid-cols-[1fr_320px] gap-6">
                    <TradeChart
                      symbol={t.symbol} signalTs={t.signal_ts} entry={t.entry_price}
                      stop={t.stop_price} target={t.target_price}
                      exitTs={t.exit_ts} exitReason={t.exit_reason}
                    />
                    <div>
                      <PayoffDiagram
                        strike={t.strike} premium={t.entry_fill ?? 0}
                        spot={t.underlying_at_exit} stop={t.stop_price} target={t.target_price}
                      />
                      <table className="w-full font-mono2 text-[11px] mt-3">
                        <tbody style={{ color: "var(--ink-secondary)" }}>
                          <tr><td className="py-0.5">contract</td><td className="text-right">{t.occ}</td></tr>
                          <tr><td className="py-0.5">delta at entry</td><td className="text-right">{t.delta_at_entry?.toFixed(3) ?? "—"}</td></tr>
                          <tr><td className="py-0.5">asked / filled</td>
                              <td className="text-right">
                                {t.limit_price?.toFixed(2) ?? "—"} / {t.entry_fill?.toFixed(2) ?? "—"}
                              </td></tr>
                          <tr><td className="py-0.5">exit asked / filled</td>
                              <td className="text-right">
                                {t.exit_limit?.toFixed(2) ?? "—"} / {t.exit_fill?.toFixed(2) ?? "—"}
                              </td></tr>
                          <tr><td className="py-0.5">debit</td><td className="text-right">{money(t.debit ?? 0)}</td></tr>
                          <tr><td className="py-0.5">fees</td><td className="text-right">{money(t.fees)}</td></tr>
                          <tr><td className="py-0.5">levels</td>
                              <td className="text-right">
                                {t.stop_price.toFixed(2)} / {t.entry_price.toFixed(2)} / {t.target_price.toFixed(2)}
                              </td></tr>
                        </tbody>
                      </table>
                      {(data?.fills[t.id] ?? []).length > 0 && (
                        <table className="w-full font-mono2 text-[10px] mt-3">
                          <tbody style={{ color: "var(--ink-muted)" }}>
                            {(data?.fills[t.id] ?? []).map((f, i) => (
                              <tr key={i}>
                                <td>{new Date(f.filled_at).toLocaleTimeString()}</td>
                                <td>{f.side.toUpperCase()}</td>
                                <td className="text-right">×{f.qty}</td>
                                <td className="text-right">@{f.price.toFixed(2)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
