"use client";

import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react/lib/core";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { useThemeTick, token } from "./theme";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

type Day = { t: number; pnl: number };

export default function DailyPnl() {
  const [days, setDays] = useState<Day[] | null>(null);
  const tick = useThemeTick();

  useEffect(() => {
    const load = () =>
      fetch("/api/daily-pnl").then((r) => r.json()).then((d) => setDays(d.days ?? [])).catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => clearInterval(id);
  }, []);

  const option = useMemo(() => {
    const d = days ?? [];
    const today = new Date().toDateString();
    return {
      animation: false,
      grid: { left: 52, right: 12, top: 12, bottom: 28 },
      tooltip: {
        trigger: "axis",
        backgroundColor: token("--surface-2", tick),
        borderColor: token("--border", tick),
        textStyle: { color: token("--ink-primary", tick), fontSize: 12 },
      },
      xAxis: {
        type: "category",
        data: d.map((x) => new Date(x.t).toLocaleDateString(undefined, { month: "short", day: "numeric" })),
        axisLine: { lineStyle: { color: token("--grid", tick) } },
        axisLabel: { color: token("--ink-muted", tick), fontSize: 11 },
      },
      yAxis: {
        type: "value",
        splitLine: { lineStyle: { color: token("--grid", tick) } },
        axisLabel: { color: token("--ink-muted", tick), fontSize: 11 },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 28,
          itemStyle: {
            borderRadius: [3, 3, 0, 0],
            color: (p: { dataIndex: number }) => {
              const day = d[p.dataIndex];
              const live = new Date(day.t).toDateString() === today;
              const c = day.pnl >= 0 ? token("--delta-up", tick) : token("--delta-down", tick);
              return live ? `${c}a6` : c;
            },
          },
          data: d.map((x) => Math.round(x.pnl * 100) / 100),
        },
      ],
    };
  }, [days, tick]);

  return (
    <div className="card p-5">
      <div className="eyebrow mb-3">daily p&amp;l · since inception</div>
      {days && days.length > 0 ? (
        <ReactECharts echarts={echarts} option={option} style={{ height: 180 }} notMerge />
      ) : (
        <div className="h-[180px] grid place-items-center text-sm" style={{ color: "var(--ink-muted)" }}>
          No sessions yet.
        </div>
      )}
    </div>
  );
}
