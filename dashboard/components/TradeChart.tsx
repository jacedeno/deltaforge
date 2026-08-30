"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { sma, type Bar } from "@/lib/sma";
import { EXTENDED_HOURS_SHADE, isExtendedHours, toLocal } from "@/lib/localtime";
import { useThemeTick, token } from "./theme";

const TIMEFRAMES = ["5Min", "15Min", "30Min", "1Hour", "1Day"] as const;

/**
 * The underlying with the signal's own levels drawn on it.
 *
 * This is the panel that answers "did it do what it was supposed to": entry,
 * the frozen 8-bar stop and the 3R target as price lines, the signal bar
 * marked, and — once closed — where the exit actually landed.
 */
export default function TradeChart({
  symbol, signalTs, entry, stop, target, exitTs, exitReason, defaultTf = "30Min",
}: {
  symbol: string;
  signalTs: string;
  entry: number;
  stop: number;
  target: number;
  exitTs?: string | null;
  exitReason?: string | null;
  defaultTf?: (typeof TIMEFRAMES)[number];
}) {
  const [tf, setTf] = useState<(typeof TIMEFRAMES)[number]>(defaultTf);
  const [bars, setBars] = useState<Bar[] | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const tick = useThemeTick();

  useEffect(() => {
    const from = new Date(Date.parse(signalTs) - 5 * 86_400_000).toISOString();
    const to = new Date(
      (exitTs ? Date.parse(exitTs) : Date.now()) + 2 * 86_400_000,
    ).toISOString();
    fetch(`/api/bars?symbol=${symbol}&tf=${tf}&from=${from}&to=${to}`)
      .then((r) => r.json())
      .then((d) => setBars(d.bars ?? []))
      .catch(() => setBars([]));
  }, [symbol, tf, signalTs, exitTs]);

  useEffect(() => {
    if (!box.current || !bars || bars.length === 0) return;
    const c = createChart(box.current, {
      height: 280,
      layout: {
        background: { color: "transparent" },
        textColor: token("--ink-secondary", tick),
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: token("--grid", tick) },
        horzLines: { color: token("--grid", tick) },
      },
      rightPriceScale: { borderColor: token("--grid", tick) },
      timeScale: { borderColor: token("--grid", tick), timeVisible: true },
    });
    chart.current = c;

    const candles = c.addSeries(CandlestickSeries, {
      upColor: token("--delta-up", tick),
      downColor: token("--delta-down", tick),
      wickUpColor: token("--delta-up", tick),
      wickDownColor: token("--delta-down", tick),
      borderVisible: false,
    });
    candles.setData(
      bars.map((b) => ({
        time: toLocal(b.t),
        open: b.o, high: b.h, low: b.l, close: b.c,
        ...(isExtendedHours(b.t) ? { color: EXTENDED_HOURS_SHADE } : {}),
      })),
    );

    for (const [period, colour] of [[21, "--series-1"], [55, "--series-2"]] as const) {
      const line = c.addSeries(LineSeries, {
        color: token(colour, tick), lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      });
      line.setData(sma(bars, period));
    }

    for (const [price, colour, title] of [
      [entry, "--level-entry", "entry"],
      [stop, "--level-stop", "stop"],
      [target, "--level-target", "3R target"],
    ] as const) {
      candles.createPriceLine({
        price, color: token(colour, tick), lineWidth: 1, lineStyle: 2,
        axisLabelVisible: true, title,
      });
    }

    const markers: { time: UTCTimestamp; position: "belowBar" | "aboveBar"; color: string; shape: "arrowUp" | "arrowDown"; text: string }[] = [
      {
        time: toLocal(Math.floor(Date.parse(signalTs) / 1000)) as UTCTimestamp,
        position: "belowBar",
        color: token("--series-2", tick),
        shape: "arrowUp",
        text: "SIGNAL",
      },
    ];
    if (exitTs) {
      markers.push({
        time: toLocal(Math.floor(Date.parse(exitTs) / 1000)) as UTCTimestamp,
        position: "aboveBar",
        color: exitReason === "target" ? token("--level-target", tick) : token("--level-stop", tick),
        shape: "arrowDown",
        text: (exitReason ?? "exit").toUpperCase(),
      });
    }
    createSeriesMarkers(candles, markers);
    c.timeScale().fitContent();

    return () => c.remove();
  }, [bars, tick, entry, stop, target, signalTs, exitTs, exitReason]);

  return (
    <div>
      <div className="flex gap-1 mb-2">
        {TIMEFRAMES.map((t) => (
          <button
            key={t}
            onClick={() => setTf(t)}
            className="font-mono2 text-[10px] px-2 py-0.5 rounded"
            style={{
              background: t === tf ? "var(--surface-2)" : "transparent",
              color: t === tf ? "var(--ink-primary)" : "var(--ink-muted)",
            }}
          >
            {t.replace("Min", "m").replace("Hour", "h").replace("Day", "d")}
          </button>
        ))}
      </div>
      {bars && bars.length === 0 ? (
        <div className="h-[280px] grid place-items-center text-sm" style={{ color: "var(--ink-muted)" }}>
          No bars for this window.
        </div>
      ) : (
        <div ref={box} />
      )}
    </div>
  );
}
