/**
 * Where DeltaForge's record begins: 2026-08-31 at $100,000, the opening
 * balance of account PA3YN2XF0XWT.
 *
 * The rebasing below is defensive rather than necessary now. It was written
 * for a borrowed account that carried months of a retired ML30 bot's P&L, and
 * the current account is clean — opened for DeltaForge, traded by nothing
 * else. It is kept because the cost is a comparison per point and the failure
 * it prevents (an inherited curve reported as this strategy's) is silent.
 *
 * The defaults are the live account's, so a missing .env.local degrades to
 * correct numbers rather than to a retired account's.
 */
export const INCEPTION_DATE = process.env.DF_INCEPTION_DATE ?? "2026-08-31";
export const INCEPTION_EQUITY = Number(process.env.DF_INCEPTION_EQUITY ?? "100000");

/**
 * Equity points at or after inception, rebased so the first is the opening
 * balance.
 *
 * Zero is dropped alongside null: the account was funded partway through
 * inception day, and Alpaca reports the hours before that as an equity of 0.
 * Kept, they drew a curve starting at nothing and leaping to $100,000, which
 * reads as a 100,000% gain the strategy never made.
 */
export function sinceInception(
  timestamps: number[],
  equity: (number | null)[],
): { t: number[]; equity: number[] } {
  const startMs = Date.parse(`${INCEPTION_DATE}T00:00:00-04:00`);
  const t: number[] = [];
  const e: number[] = [];
  for (let i = 0; i < timestamps.length; i++) {
    const v = equity[i];
    if (v == null || v <= 0 || timestamps[i] * 1000 < startMs) continue;
    t.push(timestamps[i]);
    e.push(v);
  }
  return { t, equity: e };
}

/** Calendar day at the exchange, `YYYY-MM-DD` — never the viewer's zone. */
export function nyDay(ms: number): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date(ms));
}

export function isBeforeInception(): boolean {
  return Date.now() < Date.parse(`${INCEPTION_DATE}T09:30:00-04:00`);
}
