# DeltaForge

Directional options overlay for the ML30 momentum signal, sized for a small
real-money account (~$3,000). Sibling of ThetaForge: where ThetaForge sells
premium (theta) across a wide book, DeltaForge buys direction (delta) on the
same validated signal, a few positions at a time, executed by hand.

**Status: backtested (roadmap step 2 done, 2026-08-28).** The strategy
analysis lives in [`docs/ANALYSIS.md`](docs/ANALYSIS.md); the backtest
engine lives in `src/deltaforge/` and its results in `reports/`. Nothing
here trades yet.

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
- Risk 4–5% of the account per position ($120–150), max 2–3 concurrent.
- Manual execution only. This repo documents; it does not place orders.

## Roadmap

1. Analysis (done — see docs/ANALYSIS.md)
2. Backtest the overlay against the validated signal history (debit spread
   vs. slightly-ITM long call vs. underlying shares)
3. Paper-trade the playbook for a few weeks alongside the screener
4. Go live at $3,000 only after 2 and 3 agree
