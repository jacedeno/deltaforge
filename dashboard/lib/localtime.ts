import type { Time } from "lightweight-charts";

// lightweight-charts renders UNIX timestamps as UTC on its time scale, so
// bar times must be pre-shifted into the viewer's zone (per-timestamp, so
// DST transitions stay correct).
export const toLocal = (utcSec: number): Time =>
  (utcSec - new Date(utcSec * 1000).getTimezoneOffset() * 60) as Time;

export const toLocalMs = (utcMs: number): number =>
  utcMs - new Date(utcMs).getTimezoneOffset() * 60_000;

// Regular trading hours are 9:30–16:00 in New York, wherever the viewer is.
const NY_TIME = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York", hour12: false, hour: "2-digit", minute: "2-digit",
});

export function isExtendedHours(utcSec: number): boolean {
  const [h, m] = NY_TIME.format(new Date(utcSec * 1000)).split(":").map(Number);
  const mins = h * 60 + m;
  return mins < 9 * 60 + 30 || mins >= 16 * 60;
}

// A faint neutral wash behind pre/after-market candles — readable on both themes.
export const EXTENDED_HOURS_SHADE = "rgba(125, 125, 145, 0.10)";
