# DeltaForge

Directional options overlay for the ML30 momentum signal. Sibling of
ThetaForge: where ThetaForge sells premium (theta) across a wide book,
DeltaForge buys direction (delta) on the same validated signal.

**Status: trading on paper since 2026-08-31.** One bot against one account —
Alpaca paper **PA3YN2XF0XWT**, $100,000, $7,000 a position across 14 slots —
running as `deltaforge-100k-bot` on AlgoTrader, with a dashboard at
<https://deltaforge.geekendzone.net>. Setup and operations are in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). The strategy analysis lives in
[`docs/ANALYSIS.md`](docs/ANALYSIS.md); the backtest engine lives in
`src/deltaforge/` and its results in `reports/`.

Headline result (real Alpaca options data, Feb 2024 → Aug 2026, identical
signal events, $3,000 account replay): the **slightly-ITM long call at 7–14
DTE and 0.55 delta** turns $3,000 into **$12,130 (+304%)** against **+66%**
for the underlying shares, over 1,000 trades.

**The debit spread — this repo's original thesis — did not survive
verification.** Its apparent +286% rested on 5 trades out of 772 and on a
cohort of implausibly cheap spreads that contributed more than all of the
profit. See "What did not survive" in [`docs/BACKTEST.md`](docs/BACKTEST.md).

Run it:

```bash
set -a; source ~/.secrets/alpaca-thetaforge-competition.env; set +a
uv run python scripts/run_phase1_underlying.py --help   # phase 1: signal on shares
uv run python scripts/backtest_overlay.py --help        # phase 2: options overlay
uv run python scripts/sweep_overlay.py --help           # phase 3: variations
```

## The one-line thesis

The ML30 cross gives three things an options structure can be anchored to —
a direction, a stop price, and a 3R target price. A bull call debit spread
with its short strike at the 3R target is the literal translation of the
system into options: it caps exactly the upside the strategy never captures
anyway, and the short leg pays for the theta.

## Ground rules

- Signals come from the 30-minute screener levels (or daily), never from
  the 5-minute variant — see the timeframe finding in the analysis.
- Position sizing is 7% of equity, 14 slots. The budget sweep found an
  inverted U peaking at 10% on a $3,000 account; 7% is the deliberate step
  down at $100,000, where the budget cap no longer doubles as an
  affordability filter. Reasoning in `docs/DEPLOYMENT.md`.
- Execution is automated. `scripts/run_paper_bot.py` places the orders; the
  dashboard narrates what it did.

## Roadmap

1. Analysis — done, see `docs/ANALYSIS.md`
2. Backtest the overlay against the validated signal history (debit spread
   vs. slightly-ITM long call vs. underlying shares) — done 2026-08-28
3. Paper-trade the playbook alongside the screener — running since 2026-08-31
4. Go live only after step 3 has produced enough sessions to judge. It has
   not: the account is days old, and the backtest says the book needs over a
   week just to reach steady state.
