# DeltaForge paper run — observations

Running log of what the live paper run (PA3PYB0A7982, $5,000, from 2026-10-05) shows, one dated entry per check. Observations first; proposed adjustments are proposals until Jose decides.

## 2026-10-05 (Mon) — open check, 11:45 CT

- Bot `active/enabled`, heartbeat 12 min, 0 failed passes. One error today: the
  13:45 UTC `CliOrder.symbol` crash on the first reprice, fixed in `e8cd00e`;
  the four UBER reprices since then went through cleanly.
- Equity $4,958.79 (-$41.21, -0.82% since inception), cash $4,520.79, $479
  deployed (10% of equity) in 2 of 15 slots.
- F 12c x7 @0.40, mid 0.35 (-$31.50, -11%); spot 12.12 sits **1.1% above the
  11.98 stop**. UBER 69c x1 @1.99, mid 2.07 (+$8.45); stop 3.3% away, target
  7.7%. Both 11 DTE, clock exit in 6 days.
- Journal and broker agree; no open orders.
- 8 scans, 31 signals, 2 entries. Skips: target_too_close 19, illiquid 5,
  over_budget 4. Most signals die on the 5% target gate, as in the backtest.
- Slippage: F filled at its limit; UBER needed all three reprices (asked 1.94,
  got 1.99, +$5 on a $194 debit, ~2.6%).
- Dashboard public URL 302 (Access), `/api/health` alive.
- Retired units `deltaforge-100k-bot`, `deltaforge-bot` inactive+disabled;
  `ml30-live-bot-v1-5m-top20` reads `failed` (stop timed out) but disabled.
