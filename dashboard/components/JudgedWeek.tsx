"use client";

import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, MarkLineComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useThemeTick, token } from "./theme";

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

type Point = { t: number; equity: number };
type JudgedTrade = {
  id: number; symbol: string; strike: number; contracts: number;
  entryTs: string | null; exitTs: string | null;
  entryFill: number | null; exitFill: number | null; debit: number | null;
  exitReason: string | null; pnl: number | null; pnlPctOfDebit: number | null;
};
type Judged = {
  window: { start: string; end: string };
  closeEquity: number | null; inceptionEquity: number;
  pnl: number | null; pnlPct: number | null;
  points: Point[]; trades: JudgedTrade[];
  stats: { closed: number; winRate: number; profitFactor: number } | null;
  error?: string;
};

const money = (v: number) =>
  `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const axisMoney = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const day = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("en-US", {
        timeZone: "America/New_York", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
      })
    : "—";

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded-lg p-4" style={{ background: "var(--surface-2)" }}>
      <div className="eyebrow mb-2">{label}</div>
      <div className="font-display text-2xl" style={{ color: tone ?? "var(--ink-primary)" }}>{value}</div>
      {sub && <div className="font-mono2 text-[11px] mt-1" style={{ color: "var(--ink-muted)" }}>{sub}</div>}
    </div>
  );
}

/**
 * The hackathon result, as the judges' window closed it.
 *
 * Everything below is read back from the record — Alpaca's portfolio history
 * for the curve, the bot's journal for the trades — and nothing is re-marked
 * to the live account. That is the point of the view: the window is closed, so
 * these numbers never move again, while the live figures above them do.
 */
export default function JudgedWeek() {
  const [d, setD] = useState<Judged | null>(null);
  const tick = useThemeTick();

  useEffect(() => {
    // Fetched once. A closed window has nothing to poll for.
    fetch("/api/judged").then((r) => r.json()).then(setD).catch(() => {});
  }, []);

  const option = useMemo(() => {
    const pts = d?.points ?? [];
    const labels = pts.map((p) => new Date(p.t).toISOString());
    const values = pts.map((p) => p.equity);
    const dayAt = (ms: number) =>
      new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
      }).format(new Date(ms));
    const seams = pts.reduce<number[]>((acc, p, i) => {
      if (i > 0 && dayAt(p.t) !== dayAt(pts[i - 1].t)) acc.push(i);
      return acc;
    }, []);

    return {
      animation: false,
      grid: { left: 56, right: 16, top: 16, bottom: 28 },
      tooltip: {
        trigger: "axis",
        backgroundColor: token("--surface-2", tick),
        borderColor: token("--border", tick),
        textStyle: { color: token("--ink-primary", tick), fontSize: 12 },
        formatter: (p: { name: string; value: number }[]) =>
          `${new Date(p[0].name).toLocaleString(undefined, { timeZone: "America/New_York" })} ET`
          + `<br/><b>${money(p[0].value)}</b>`,
      },
      xAxis: {
        type: "category", data: labels, boundaryGap: false,
        axisLine: { lineStyle: { color: token("--grid", tick) } },
        axisTick: { show: false },
        axisLabel: {
          color: token("--ink-muted", tick), fontSize: 11, hideOverlap: true,
          formatter: (iso: string) =>
            new Date(iso).toLocaleString("en-US", {
              timeZone: "America/New_York", month: "short", day: "numeric", hour: "2-digit", hour12: false,
            }),
        },
      },
      yAxis: {
        type: "value", scale: true,
        splitLine: { lineStyle: { color: token("--grid", tick) } },
        axisLabel: { color: token("--ink-muted", tick), fontSize: 11, formatter: axisMoney },
      },
      series: [
        {
          type: "line", showSymbol: false, smooth: false,
          lineStyle: { width: 2, color: token("--series-1", tick) },
          areaStyle: { color: token("--series-1", tick), opacity: 0.08 },
          data: values,
          markLine: {
            silent: true, symbol: "none",
            lineStyle: { color: token("--baseline", tick), type: "dashed", width: 1 },
            label: { show: false },
            data: [
              { yAxis: d?.inceptionEquity ?? 100000 },
              ...seams.map((i) => ({
                xAxis: i,
                lineStyle: { color: token("--grid", tick), type: "solid" as const, width: 1 },
              })),
            ],
          },
        },
      ],
    };
  }, [d, tick]);

  const up = (d?.pnl ?? 0) >= 0;

  return (
    <section className="card p-5 space-y-4" style={{ borderColor: "var(--accent)" }}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="eyebrow">hackathon result · judged close</div>
          <div className="font-mono2 text-[11px] mt-1" style={{ color: "var(--ink-muted)" }}>
            Alpaca AI Trading Agents Hackathon · sessions {d?.window?.start ?? "2026-08-31"} → {d?.window?.end ?? "2026-09-03"},
            measured at the Thursday close · account PA3YN2XF0XWT
          </div>
        </div>
        <div className="font-mono2 text-[11px] px-2.5 py-1 rounded-md"
             style={{ background: "var(--surface-2)", color: "var(--ink-secondary)", border: "1px solid var(--border)" }}>
          final · does not update
        </div>
      </div>

      {d?.error && (
        <div className="font-mono2 text-[12px]" style={{ color: "var(--critical)" }}>{d.error}</div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Tile
          label="equity at the close"
          value={d?.closeEquity != null ? money(d.closeEquity) : "—"}
          sub={d ? `from ${money(d.inceptionEquity)} at inception` : undefined}
          tone={up ? "var(--delta-up)" : "var(--delta-down)"}
        />
        <Tile
          label="profit"
          value={d?.pnl != null ? `${d.pnl >= 0 ? "+" : ""}${money(d.pnl)}` : "—"}
          sub={d?.pnlPct != null ? `${d.pnlPct >= 0 ? "+" : "−"}${Math.abs(d.pnlPct).toFixed(2)}%` : undefined}
          tone={up ? "var(--delta-up)" : "var(--delta-down)"}
        />
        <Tile
          label="positions closed"
          value={d?.stats ? String(d.stats.closed) : "—"}
          sub={d?.stats ? `${(d.stats.winRate * 100).toFixed(0)}% winners` : undefined}
        />
        <Tile
          label="open at the close"
          value="0"
          sub="book closed to cash for judging"
        />
      </div>

      {d && d.points.length > 1 ? (
        <ReactECharts echarts={echarts} option={option} style={{ height: 260 }} notMerge />
      ) : (
        <div className="h-[260px] grid place-items-center text-sm" style={{ color: "var(--ink-muted)" }}>
          {d ? "The judged curve is no longer in Alpaca's intraday retention." : "Loading the judged week…"}
        </div>
      )}

      <div>
        <div className="eyebrow mb-3">every position of the judged week</div>
        <div className="overflow-x-auto">
          <table className="w-full font-mono2 text-[11px]">
            <thead>
              <tr style={{ color: "var(--ink-muted)" }}>
                {["", "opened", "closed", "contracts", "in", "out", "exit", "P&L", "on debit"].map((h) => (
                  <th key={h} className="text-left font-normal pb-2 pr-4 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(d?.trades ?? []).map((t) => {
                const win = (t.pnl ?? 0) >= 0;
                return (
                  <tr key={t.id} className="border-t" style={{ borderColor: "var(--grid)" }}>
                    <td className="py-2 pr-4 font-display font-semibold whitespace-nowrap"
                        style={{ color: "var(--ink-primary)" }}>
                      {t.symbol} {t.strike}c
                    </td>
                    <td className="py-2 pr-4 whitespace-nowrap" style={{ color: "var(--ink-secondary)" }}>{day(t.entryTs)}</td>
                    <td className="py-2 pr-4 whitespace-nowrap" style={{ color: "var(--ink-secondary)" }}>{day(t.exitTs)}</td>
                    <td className="py-2 pr-4" style={{ color: "var(--ink-secondary)" }}>×{t.contracts}</td>
                    <td className="py-2 pr-4" style={{ color: "var(--ink-secondary)" }}>{t.entryFill?.toFixed(2) ?? "—"}</td>
                    <td className="py-2 pr-4" style={{ color: "var(--ink-secondary)" }}>{t.exitFill?.toFixed(2) ?? "—"}</td>
                    <td className="py-2 pr-4" style={{ color: "var(--ink-muted)" }}>{t.exitReason ?? "—"}</td>
                    <td className="py-2 pr-4 whitespace-nowrap"
                        style={{ color: win ? "var(--delta-up)" : "var(--delta-down)" }}>
                      {t.pnl == null ? "—" : money(t.pnl)}
                    </td>
                    <td className="py-2 pr-4" style={{ color: "var(--ink-muted)" }}>
                      {t.pnlPctOfDebit == null ? "—" : `${t.pnlPctOfDebit >= 0 ? "+" : "−"}${Math.abs(t.pnlPctOfDebit).toFixed(0)}%`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {/* The exits all read MANUAL because the protective floor closed the
            book on judging day rather than each position reaching its own
            stop or target — said here so the tag is not mistaken for a hand
            on the keyboard. */}
        <p className="text-[11px] mt-3" style={{ color: "var(--ink-muted)" }}>
          Every entry was the agent&apos;s own. The <span className="font-mono2">manual</span> exits are the
          coded protective floor closing the book to cash on judging day, not a human clicking sell.
        </p>
      </div>
    </section>
  );
}
