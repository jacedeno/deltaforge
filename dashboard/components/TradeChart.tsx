"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LogicalRange,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { daysToCover, sma, type Bar } from "@/lib/sma";
import {
  ANCHOR_COLOURS, avwap, loadAnchors, saveAnchors, type Anchor,
} from "@/lib/avwap";
import { EXTENDED_HOURS_SHADE, isExtendedHours, toLocal } from "@/lib/localtime";
import { useThemeTick, token } from "./theme";

const TIMEFRAMES = ["5Min", "15Min", "30Min", "1Hour", "1Day"] as const;
type Tf = (typeof TIMEFRAMES)[number];

const DAY = 86_400_000;
const FAST = 21;
const SLOW = 55;
// How far from the left edge, in bars, panning starts pulling older history.
const PREFETCH_MARGIN = 10;

type Marker = {
  time: UTCTimestamp;
  position: "belowBar" | "aboveBar";
  color: string;
  shape: "arrowUp" | "arrowDown";
  text: string;
};

/** Merge an older chunk in front of what is loaded, dropping overlaps. */
function prepend(older: Bar[], current: Bar[]): Bar[] {
  const seen = new Set(current.map((b) => b.t));
  const add = older.filter((b) => !seen.has(b.t));
  return add.length === 0 ? current : [...add, ...current].sort((a, b) => a.t - b.t);
}

/**
 * Index of the bar *containing* `sec` — the last one opening at or before it.
 *
 * Not an equality test on purpose: the signal is stamped on a 30-minute close,
 * so on any other timeframe it falls inside a bar rather than on its edge, and
 * a marker placed at the raw timestamp would float between candles (or, on the
 * daily frame, land on a time no bar occupies).
 */
function barIndexAt(bars: Bar[], sec: number): number {
  let idx = -1;
  for (let i = 0; i < bars.length && bars[i].t <= sec; i++) idx = i;
  return idx;
}

/** Default label for a new anchor: the bar it sits on, in the viewer's zone. */
function anchorLabel(sec: number): string {
  return new Date(sec * 1000).toLocaleString(undefined, {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

/**
 * The underlying with the signal's own levels drawn on it.
 *
 * This is the panel that answers "did it do what it was supposed to": entry,
 * the frozen 8-bar stop and the 3R target as price lines, the signal bar
 * marked, and — once closed — where the exit actually landed.
 *
 * The chart holds more history than it shows. The SMAs are the bot's own 21
 * and 55 over 30-minute bars, and a 55-period average needs 55 bars behind the
 * first visible candle; fetching only the display window left SMA21 starting a
 * third of the way in and SMA55 mostly or entirely absent. Panning left pulls
 * older bars in rather than running off the end of the data.
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
  defaultTf?: Tf;
}) {
  const [tf, setTf] = useState<Tf>(defaultTf);
  const [bars, setBars] = useState<Bar[] | null>(null);
  const [anchors, setAnchors] = useState<Anchor[]>([]);
  const [arming, setArming] = useState(false);
  // Consolidated-volume copy of the same window, fetched only once an anchor
  // exists. Null means "fall back to the IEX bars already on screen".
  const [volBars, setVolBars] = useState<Bar[] | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candles = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lines = useRef<ISeriesApi<"Line">[]>([]);
  const markers = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const vwaps = useRef(new Map<string, ISeriesApi<"Line">>());
  const tick = useThemeTick();

  // Refs, not state: the pan handler reads them without re-subscribing.
  const oldest = useRef(0);        // oldest instant already requested
  const exhausted = useRef(false); // the symbol has no more history
  const loading = useRef(false);
  const framed = useRef(false);    // the opening visible range has been set

  const intraday = tf !== "1Day";

  // Memoised: `Date.now()` in a render-time expression would change identity
  // every pass and re-trigger the fetch effect forever.
  const [windowStart, windowEnd] = useMemo(
    () => [
      Date.parse(signalTs) - 5 * DAY,
      (exitTs ? Date.parse(exitTs) : Date.now()) + 2 * DAY,
    ],
    [signalTs, exitTs],
  );

  const fetchBars = useCallback(
    async (from: number, to: number): Promise<Bar[]> => {
      const q = new URLSearchParams({
        symbol, tf,
        from: new Date(from).toISOString(),
        to: new Date(to).toISOString(),
      });
      try {
        const r = await fetch(`/api/bars?${q}`).then((x) => x.json());
        return (r.bars ?? []) as Bar[];
      } catch {
        return [];
      }
    },
    [symbol, tf],
  );

  // Initial load: the display window, plus enough history behind it that the
  // 55-period SMA is already defined on the first candle the viewer sees.
  useEffect(() => {
    let cancelled = false;
    const from = windowStart - daysToCover(SLOW, tf) * DAY;
    framed.current = false;
    exhausted.current = false;
    oldest.current = from;
    setBars(null);
    fetchBars(from, windowEnd).then((b) => {
      if (!cancelled) setBars(b);
    });
    return () => { cancelled = true; };
  }, [fetchBars, tf, windowStart, windowEnd]);

  // Anchors are per symbol and outlive the page — see lib/avwap.
  useEffect(() => {
    setAnchors(loadAnchors(symbol));
  }, [symbol]);

  const update = useCallback(
    (next: Anchor[]) => {
      setAnchors(next);
      saveAnchors(symbol, next);
    },
    [symbol],
  );

  const loadOlder = useCallback(async () => {
    if (loading.current || exhausted.current) return;
    loading.current = true;
    const to = oldest.current;
    const from = to - daysToCover(300, tf) * DAY;
    const older = await fetchBars(from, to);
    oldest.current = from;
    if (older.length === 0) exhausted.current = true;
    else setBars((prev) => prepend(older, prev ?? []));
    loading.current = false;
  }, [fetchBars, tf]);

  // Chart, series and price lines — built once and kept. Rebuilding it on
  // every data change would throw away the viewer's zoom on each fetch.
  useEffect(() => {
    if (!box.current) return;
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

    const s = c.addSeries(CandlestickSeries, {
      upColor: token("--delta-up", tick),
      downColor: token("--delta-down", tick),
      wickUpColor: token("--delta-up", tick),
      wickDownColor: token("--delta-down", tick),
      borderVisible: false,
    });
    candles.current = s;

    // SMA21 blue, SMA55 orange. The slow one is drawn thicker: it is the line
    // price has to cross for the entry to fire at all, where the fast one only
    // confirms.
    lines.current = ([["--sma-fast", 1], ["--sma-slow", 2]] as const).map(([colour, width]) =>
      c.addSeries(LineSeries, {
        color: token(colour, tick),
        lineWidth: width,
        priceLineVisible: false,
        lastValueVisible: false,
      }),
    );

    for (const [price, colour, title] of [
      [entry, "--level-entry", "entry"],
      [stop, "--level-stop", "stop"],
      [target, "--level-target", "3R target"],
    ] as const) {
      s.createPriceLine({
        price, color: token(colour, tick), lineWidth: 1, lineStyle: 2,
        axisLabelVisible: true, title,
      });
    }

    markers.current = createSeriesMarkers(s, []);
    framed.current = false;

    return () => {
      c.remove();
      chart.current = null;
      candles.current = null;
      lines.current = [];
      markers.current = null;
      // The VWAP handles died with the chart; dropping them stops the sync
      // effect from calling removeSeries on a destroyed chart.
      vwaps.current.clear();
    };
  }, [tick, entry, stop, target]);

  // Consolidated volume for the anchored VWAPs. Prices stay IEX — only the
  // weights come from SIP, and only when there is an anchor to weight.
  useEffect(() => {
    if (anchors.length === 0 || !bars || bars.length === 0) {
      setVolBars(null);
      return;
    }
    let cancelled = false;
    const from = bars[0].t * 1000;
    // The account's entitlement covers historical SIP but not its last 15
    // minutes, so the request stops short of that; the tail keeps IEX weights.
    const to = Math.min(bars[bars.length - 1].t * 1000 + 60_000, Date.now() - 16 * 60_000);
    if (to <= from) {
      setVolBars(null);
      return;
    }
    const q = new URLSearchParams({
      symbol, tf, feed: "sip",
      from: new Date(from).toISOString(),
      to: new Date(to).toISOString(),
    });
    fetch(`/api/bars?${q}`)
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setVolBars((d.bars ?? []).length > 0 ? (d.bars as Bar[]) : null);
      })
      .catch(() => {
        if (!cancelled) setVolBars(null);
      });
    return () => { cancelled = true; };
  }, [anchors.length, bars, symbol, tf]);

  // Arm, then click a candle to anchor there. Without arming, a click on the
  // chart does nothing — panning would otherwise drop anchors everywhere.
  useEffect(() => {
    const c = chart.current;
    if (!c || !arming || !bars || bars.length === 0) return;
    const onClick = (p: MouseEventParams) => {
      if (typeof p.logical !== "number") return;
      const idx = Math.round(p.logical);
      if (idx < 0 || idx >= bars.length) return;
      const t = bars[idx].t;
      setArming(false);
      if (anchors.some((a) => a.t === t)) return;
      update([
        ...anchors,
        {
          id: `${t}`,
          t,
          name: anchorLabel(t),
          color: ANCHOR_COLOURS[anchors.length % ANCHOR_COLOURS.length],
        },
      ]);
    };
    c.subscribeClick(onClick);
    return () => c.unsubscribeClick(onClick);
  }, [arming, bars, anchors, update, tick]);

  // One line series per anchor, rebuilt whenever the anchors, the data or the
  // theme change. A handful of anchors makes the churn cheaper than diffing.
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    for (const s of vwaps.current.values()) {
      try { c.removeSeries(s); } catch { /* chart already torn down */ }
    }
    vwaps.current.clear();

    const src = volBars ?? bars;
    if (!src || src.length === 0) return;
    for (const a of anchors) {
      const idx = barIndexAt(src, a.t);
      if (idx < 0) continue;
      const s = c.addSeries(LineSeries, {
        color: a.color,
        lineWidth: 2,
        title: a.name,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      s.setData(avwap(src, idx));
      vwaps.current.set(a.id, s);
    }
  }, [anchors, bars, volBars, tick]);

  // Pull older bars when the viewer pans or zooms toward the left edge.
  useEffect(() => {
    const c = chart.current;
    if (!c) return;
    const onRange = (r: LogicalRange | null) => {
      if (r && r.from < PREFETCH_MARGIN) void loadOlder();
    };
    c.timeScale().subscribeVisibleLogicalRangeChange(onRange);
    return () => c.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
  }, [loadOlder, tick, entry, stop, target]);

  // Data, SMAs and markers. Separate from creation so a fetch updates the
  // chart in place.
  useEffect(() => {
    const c = chart.current;
    const s = candles.current;
    if (!c || !s || !bars || bars.length === 0) return;

    const scale = c.timeScale();
    const had = s.data().length;
    const previous = framed.current ? scale.getVisibleLogicalRange() : null;

    // The bar the entry fired on: price closed above SMA55 having been under it
    // on the bar before, above SMA21, on a bullish candle. Painted in full so
    // it is findable at a glance instead of being inferred from the arrow.
    const entryIdx = barIndexAt(bars, Math.floor(Date.parse(signalTs) / 1000));
    const entryColour = token("--series-2", tick);

    s.setData(
      bars.map((b, i) => ({
        time: toLocal(b.t),
        open: b.o, high: b.h, low: b.l, close: b.c,
        ...(i === entryIdx
          ? { color: entryColour, borderColor: entryColour, wickColor: entryColour }
          : intraday && isExtendedHours(b.t)
            ? { color: EXTENDED_HOURS_SHADE }
            : {}),
      })),
    );
    lines.current[0]?.setData(sma(bars, FAST, intraday));
    lines.current[1]?.setData(sma(bars, SLOW, intraday));

    const marks: Marker[] = [];
    if (entryIdx >= 0) {
      marks.push({
        time: toLocal(bars[entryIdx].t) as UTCTimestamp,
        position: "belowBar",
        color: entryColour,
        shape: "arrowUp",
        text: "ENTRY",
      });
    }
    const exitIdx = exitTs ? barIndexAt(bars, Math.floor(Date.parse(exitTs) / 1000)) : -1;
    if (exitIdx >= 0) {
      marks.push({
        time: toLocal(bars[exitIdx].t) as UTCTimestamp,
        position: "aboveBar",
        color: exitReason === "target" ? token("--level-target", tick) : token("--level-stop", tick),
        shape: "arrowDown",
        text: (exitReason ?? "exit").toUpperCase(),
      });
    }
    markers.current?.setMarkers(marks);

    if (!framed.current) {
      // Open on the trade, not on the warm-up history behind it.
      const first = bars[0].t;
      const last = bars[bars.length - 1].t;
      scale.setVisibleRange({
        from: toLocal(Math.max(Math.floor(windowStart / 1000), first)),
        to: toLocal(Math.min(Math.floor(windowEnd / 1000), last)),
      });
      framed.current = true;
    } else if (previous) {
      // Older bars arrived: shift the view by however many were prepended so
      // the candles under the cursor stay where they were.
      const added = bars.length - had;
      scale.setVisibleLogicalRange({
        from: previous.from + added,
        to: previous.to + added,
      });
    }
  }, [bars, tick, intraday, windowStart, windowEnd, signalTs, exitTs, exitReason]);

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
        <button
          onClick={() => setArming((a) => !a)}
          className="font-mono2 text-[10px] px-2 py-0.5 rounded ml-auto"
          style={{
            background: arming ? "var(--accent)" : "transparent",
            color: arming ? "var(--page)" : "var(--ink-muted)",
          }}
          title="Anchored VWAP: arm, then click the candle to anchor to"
        >
          {arming ? "click a candle…" : "⚓ anchor VWAP"}
        </button>
      </div>
      <div className="relative" style={{ cursor: arming ? "crosshair" : undefined }}>
        <div ref={box} />
        {bars && bars.length === 0 && (
          <div
            className="absolute inset-0 grid place-items-center text-sm"
            style={{ color: "var(--ink-muted)" }}
          >
            No bars for this window.
          </div>
        )}
      </div>
      {anchors.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mt-2">
          {anchors.map((a) => (
            <span
              key={a.id}
              className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded"
              style={{ background: "var(--surface-2)" }}
            >
              <span
                style={{
                  background: a.color, width: 8, height: 8, borderRadius: 2, flex: "none",
                }}
              />
              <input
                value={a.name}
                onChange={(e) =>
                  update(anchors.map((x) => (x.id === a.id ? { ...x, name: e.target.value } : x)))
                }
                className="font-mono2 text-[10px] bg-transparent outline-none"
                style={{ color: "var(--ink-secondary)", width: `${Math.max(a.name.length, 4)}ch` }}
                aria-label="anchor name"
              />
              <button
                onClick={() => update(anchors.filter((x) => x.id !== a.id))}
                className="text-[10px] leading-none"
                style={{ color: "var(--ink-muted)" }}
                aria-label={`remove ${a.name}`}
              >
                ×
              </button>
            </span>
          ))}
          <span className="font-mono2 text-[10px]" style={{ color: "var(--ink-muted)" }}>
            volume: {volBars ? "SIP" : "IEX"}
          </span>
        </div>
      )}
    </div>
  );
}
