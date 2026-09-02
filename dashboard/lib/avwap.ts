import type { Time } from "lightweight-charts";
import type { Bar } from "./sma";
import { toLocal } from "./localtime";

/**
 * Anchored VWAP — a volume-weighted average running from one chosen bar
 * forward, rather than resetting each session.
 *
 * Unlike the SMAs, this is not a strategy input: the bot never reads it. It is
 * a market level, so it is weighted on consolidated (SIP) volume and counts
 * extended hours, where the SMAs deliberately mirror the bot's regular-hours
 * IEX view. Two different questions, two different rules.
 */
export function avwap(bars: Bar[], fromIdx: number): { time: Time; value: number }[] {
  const out: { time: Time; value: number }[] = [];
  let pv = 0;
  let vol = 0;
  for (let i = Math.max(0, fromIdx); i < bars.length; i++) {
    const b = bars[i];
    pv += ((b.h + b.l + b.c) / 3) * b.v;
    vol += b.v;
    if (vol > 0) out.push({ time: toLocal(b.t), value: pv / vol });
  }
  return out;
}

export type Anchor = {
  id: string;
  t: number;      // anchor bar's UNIX seconds — a time, never a bar index, so
  name: string;   // the anchor survives a timeframe change
  color: string;
};

// Enough to tell several anchors apart at a glance without reaching for the
// palette the SMAs and levels already occupy.
export const ANCHOR_COLOURS = [
  "#e0b32d", "#25b6a8", "#d4569b", "#7a9c4a", "#9b7ce0", "#c96a3a",
];

const KEY = (symbol: string) => `deltaforge.avwap.${symbol}`;

/**
 * Anchors persist per symbol, not per trade: a level anchored on DELL's pivot
 * low is a fact about DELL, and should still be there on the next DELL signal.
 *
 * localStorage keeps them to this browser. Every access is guarded — Safari's
 * private mode throws on read as well as write.
 */
export function loadAnchors(symbol: string): Anchor[] {
  try {
    const raw = localStorage.getItem(KEY(symbol));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (a): a is Anchor =>
        !!a && typeof a.id === "string" && typeof a.t === "number" &&
        typeof a.name === "string" && typeof a.color === "string",
    );
  } catch {
    return [];
  }
}

export function saveAnchors(symbol: string, anchors: Anchor[]): void {
  try {
    localStorage.setItem(KEY(symbol), JSON.stringify(anchors));
  } catch {
    // Storage full or blocked: the anchors still work for this session.
  }
}
