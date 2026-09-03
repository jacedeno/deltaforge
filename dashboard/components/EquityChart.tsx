"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ReactECharts from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent, MarkLineComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useThemeTick, token } from "./theme";

echarts.use([LineChart, GridComponent, TooltipComponent, MarkLineComponent, CanvasRenderer]);

type Point = { t: number; equity: number };
const RANGES = ["1D", "1W", "1M", "ALL"] as const;

const money = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export default function EquityChart() {
  const [range, setRange] = useState<(typeof RANGES)[number]>("1W");
  const [data, setData] = useState<{ points: Point[]; fellBack?: boolean; note?: string } | null>(null);
  const tick = useThemeTick();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = () =>
      fetch(`/api/equity?range=${range}`).then((r) => r.json()).then(setData).catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, [range]);

  const option = useMemo(() => {
    const pts = data?.points ?? [];
    const inception = pts.length ? pts[0].equity : 0;
    const intraday = range === "1D" || range === "1W";

    // A time axis gives the overnight gap real width, so a two-day week drew
    // 17 dead hours between sessions as a long flat run and squeezed the
    // trading into the margins. On a category axis one session butts against
    // the next and every pixel is a minute the market was open.
    const labels = pts.map((p) => new Date(p.t).toISOString());
    const values = pts.map((p) => p.equity);

    const dayAt = (ms: number) =>
      new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
      }).format(new Date(ms));

    // Where one session ends and the next begins — with the gap closed, the
    // seam needs saying out loud or a jump overnight reads as a jump in trade.
    const seams = intraday
      ? pts.reduce<number[]>((acc, p, i) => {
          if (i > 0 && dayAt(p.t) !== dayAt(pts[i - 1].t)) acc.push(i);
          return acc;
        }, [])
      : [];

    const fmt = (iso: string) =>
      new Date(iso).toLocaleString(undefined, {
        timeZone: "America/New_York",
        ...(intraday
          ? { hour: "2-digit", minute: "2-digit", hour12: false }
          : { month: "short", day: "numeric" }),
      });

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
        type: "category",
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: token("--grid", tick) } },
        axisTick: { show: false },
        axisLabel: {
          color: token("--ink-muted", tick),
          fontSize: 11,
          hideOverlap: true,
          formatter: fmt,
        },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitLine: { lineStyle: { color: token("--grid", tick) } },
        axisLabel: { color: token("--ink-muted", tick), fontSize: 11, formatter: money },
      },
      series: [
        {
          type: "line",
          showSymbol: false,
          smooth: false,
          lineStyle: { width: 2, color: token("--series-1", tick) },
          areaStyle: { color: token("--series-1", tick), opacity: 0.08 },
          data: values,
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: token("--baseline", tick), type: "dashed", width: 1 },
            label: { show: false },
            data: [
              // The opening balance, so every glance answers "up or down since
              // we started".
              { yAxis: inception },
              // One per session seam.
              ...seams.map((i) => ({
                xAxis: i,
                lineStyle: { color: token("--grid", tick), type: "solid" as const, width: 1 },
              })),
            ],
          },
        },
      ],
    };
  }, [data, tick, range]);

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="eyebrow">
          equity{data?.fellBack ? " · shortest range with data" : ""}
        </span>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className="font-mono2 text-[11px] px-2 py-1 rounded"
              style={{
                background: r === range ? "var(--surface-2)" : "transparent",
                color: r === range ? "var(--ink-primary)" : "var(--ink-muted)",
              }}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      {data && data.points.length > 1 ? (
        <ReactECharts
          echarts={echarts}
          option={option}
          style={{ height: 260 }}
          notMerge
          ref={ref as never}
        />
      ) : (
        <div
          className="h-[260px] grid place-items-center text-sm text-center px-6"
          style={{ color: "var(--ink-muted)" }}
        >
          {data?.note ?? "The curve starts once DeltaForge has traded."}
        </div>
      )}
    </div>
  );
}
