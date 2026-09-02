import type { Time } from "lightweight-charts";
import { isExtendedHours, toLocal } from "./localtime";

export type Bar = { t: number; o: number; h: number; l: number; c: number; v: number };

/**
 * Simple moving average, matching the bot: 21/55 over regular-hours 30m bars.
 *
 * The bot computes its SMAs on RTH bars (ml30 filters extended hours out), so
 * an overlay that averaged pre/after-market prints would draw a line the
 * strategy never saw and quietly disagree with every signal marker.
 *
 * `intraday` must be false for daily bars. Alpaca stamps them 00:00 New York,
 * which the RTH test reads as extended hours — filtering every last one out
 * and leaving the daily chart with no SMA at all.
 */
export function sma(
  bars: Bar[],
  period: number,
  intraday: boolean,
): { time: Time; value: number }[] {
  const src = intraday ? bars.filter((b) => !isExtendedHours(b.t)) : bars;
  const out: { time: Time; value: number }[] = [];
  let sum = 0;
  for (let i = 0; i < src.length; i++) {
    sum += src[i].c;
    if (i >= period) sum -= src[i - period].c;
    if (i >= period - 1) out.push({ time: toLocal(src[i].t), value: sum / period });
  }
  return out;
}

// RTH bars each timeframe yields per session, used to size the history the
// chart must hold before the first visible candle for SMA55 to be defined.
export const RTH_BARS_PER_DAY: Record<string, number> = {
  "5Min": 78, "15Min": 26, "30Min": 13, "1Hour": 7, "1Day": 1,
};

/**
 * Calendar days of history covering `bars` bars, with weekends and holidays.
 *
 * The 1.5 stretches trading days into calendar days; the +5 is holiday slack.
 * A tighter cushion left the hourly and daily frames at 60 and 56 bars of
 * warm-up against a 55-period average — enough only until a holiday week.
 */
export function daysToCover(bars: number, tf: string): number {
  const perDay = RTH_BARS_PER_DAY[tf] ?? 13;
  return Math.ceil((bars / perDay) * 1.5) + 5;
}
