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

/** Equity points at or after inception, rebased so the first is the opening balance. */
export function sinceInception(
  timestamps: number[],
  equity: (number | null)[],
): { t: number[]; equity: number[] } {
  const startMs = Date.parse(`${INCEPTION_DATE}T00:00:00-04:00`);
  const t: number[] = [];
  const e: number[] = [];
  for (let i = 0; i < timestamps.length; i++) {
    const v = equity[i];
    if (v == null || timestamps[i] * 1000 < startMs) continue;
    t.push(timestamps[i]);
    e.push(v);
  }
  return { t, equity: e };
}

export function isBeforeInception(): boolean {
  return Date.now() < Date.parse(`${INCEPTION_DATE}T09:30:00-04:00`);
}
