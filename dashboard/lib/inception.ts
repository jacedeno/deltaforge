/**
 * Where DeltaForge's record begins.
 *
 * The Alpaca account is not new — it ran a retired ML30 fractional paper bot
 * until 2026-08-30, and its portfolio history still carries those months.
 * Everything this dashboard reports is measured from inception instead, so the
 * curve starts flat at the opening balance rather than inheriting a stranger's
 * P&L. Trades are naturally clean already: the journal is DeltaForge's own and
 * starts empty.
 */
export const INCEPTION_DATE = process.env.DF_INCEPTION_DATE ?? "2026-08-31";
export const INCEPTION_EQUITY = Number(process.env.DF_INCEPTION_EQUITY ?? "3030.85");

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
