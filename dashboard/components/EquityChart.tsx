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
    return {
      animation: false,
      grid: { left: 56, right: 16, top: 16, bottom: 28 },
      tooltip: {
        trigger: "axis",
        backgroundColor: token("--surface-2", tick),
        borderColor: token("--border", tick),
        textStyle: { color: token("--ink-primary", tick), fontSize: 12 },
        formatter: (p: { value: [number, number] }[]) =>
          `${new Date(p[0].value[0]).toLocaleString()}<br/><b>${money(p[0].value[1])}</b>`,
      },
      xAxis: {
        type: "time",
        axisLine: { lineStyle: { color: token("--grid", tick) } },
        axisLabel: { color: token("--ink-muted", tick), fontSize: 11 },
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
          data: pts.map((p) => [p.t, p.equity]),
          // The opening balance, so every glance answers "up or down since we started".
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: token("--baseline", tick), type: "dashed", width: 1 },
            label: { show: false },
            data: [{ yAxis: inception }],
          },
        },
      ],
    };
  }, [data, tick]);

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
