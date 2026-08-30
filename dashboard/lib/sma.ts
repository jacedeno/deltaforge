import type { Time } from "lightweight-charts";
import { isExtendedHours, toLocal } from "./localtime";

export type Bar = { t: number; o: number; h: number; l: number; c: number };

/**
 * Simple moving average over regular-hours bars only.
 *
 * The bot computes its SMAs on RTH bars (ml30 filters extended hours out), so
 * an overlay that averaged pre/after-market prints would draw a line the
 * strategy never saw and quietly disagree with every signal marker.
 */
export function sma(bars: Bar[], period: number): { time: Time; value: number }[] {
  const rth = bars.filter((b) => !isExtendedHours(b.t));
  const out: { time: Time; value: number }[] = [];
  let sum = 0;
  for (let i = 0; i < rth.length; i++) {
    sum += rth[i].c;
    if (i >= period) sum -= rth[i - period].c;
    if (i >= period - 1) out.push({ time: toLocal(rth[i].t), value: sum / period });
  }
  return out;
}
