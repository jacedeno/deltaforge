# Backtesting the Options Overlay

> Results, 2026-08-29. The counterpart to [`ANALYSIS.md`](ANALYSIS.md):
> that document reasoned about what the overlay *should* be, this one
> reports what the historical data says it *was*. Roadmap step 2.

## What was run

Three structures over **identical signal events**, so nothing separates them
but the instrument:

| | Instrument |
|---|---|
| `debit_spread` | Long call near the signal price, short call at the 3R target |
| `long_call` | Single slightly-ITM call |
| `shares` | The underlying, as the ML30 system trades it today |

Two phases, because the analysis stacked two unvalidated layers:

1. **Phase 1** validated the 30-minute ML30 signal on the underlying (it had
   never been backtested — only 5m and 15m were).
2. **Phase 2** replayed the options overlay on Phase 1's own signal stream.

Every run writes `<label>_{trades,equity_curve,stats,config}.json` under
`reports/`, with both repos' commit SHAs and the calibration files' contents
embedded in the config artifact.

## Phase 1 — the 30-minute signal does have an edge

45 sub-$150 names, 2020-01 → 2026-08, 30-minute SIP bars.

| | $3,000 account (3 slots) | Uncapped signal stream |
|---|---|---|
| Trades | 830 | 6,724 |
| Profit factor | 1.395 | 1.330 |
| Expectancy | 0.267 R | 0.162 R |
| Target-touch rate | 31.7% | 29.1% |
| Max drawdown | 23.1% | — |
| Final equity | $18,788 (+526%) | — |

Two findings that mattered more than the headline:

- **Median trade duration is 2–3 trading days** (p90: 13–15). The 14–21 DTE
  assumption in ANALYSIS.md comfortably contains the typical trade — the
  overlay is not fighting the clock.
- **2026 is the only losing year** (−0.14 R, PF 0.82 on the benchmark). The
  live account being flat for a month is the year, not a broken bot.

**Caveat carried forward:** under the −1.3 R stop-fill sensitivity (live
fills averaged −1.315 R against a modelled −1.00 R), the uncapped stream's
expectancy goes to −0.05 R. The edge in shares is real but thin, and it is
thinnest exactly where execution is worst. This is an argument *for* the
overlay, where the maximum loss is the debit and there is no stop order in
the underlying to be slipped.

## Phase 2 — the real-data window (Feb 2024 → Aug 2026)

2,565 signal events, real Alpaca option bars, $3,000 portfolio replay
(3 slots, one position per underlying, max debit $150), fill haircut 0.5.

| | Debit spread | Shares | Long call |
|---|---|---|---|
| Final equity | **$11,578** | $4,976 | $4,531 |
| Return | **+286%** | +66% | +51% |
| Profit factor | 1.32 | 1.47 | 1.14 |
| Max drawdown | −22% | −23% | −15% |
| Trades taken | 399 | 274 | 234 |

### The number ANALYSIS.md said needed measuring

> "Stops on the underlying do not map linearly to spread value — the −40 to
> −60% loss-at-stop estimate needs measuring, not assuming."

Measured, over 491 stop exits: **median −35% of debit** (mean −32%, p10
−65%, p90 −5%). Better than assumed. With 64% of trades ending at a stop,
this cushion is most of where the overlay's advantage over shares comes
from — a stop in shares costs a full R, a stop in the spread costs about a
third of the debit.

At target exits the spread returns **+70% of debit** on average, capturing
37% of the theoretical maximum (it exits on the touch, not at expiry — as
the playbook specifies).

### Costs and data quality

- **Fee drag: 11.6% of gross gains** ($3,632 on 399 trades). Real, survivable.
- **Mark sources**: 61.9% real minute bars, 30.6% Black-Scholes anchored to
  an observed IV, 4.9% fully modelled, 2.6% daily bars. The result rests
  mostly on real prints.
- **65% of events were skipped for exceeding the $150 debit budget.** This,
  not signal quality, is the binding constraint at $3,000 — the account
  effectively trades the cheap half of the universe.

## The fill model is the load-bearing assumption

**Alpaca keeps no historical option bid/ask.** It serves trade-derived bars
from Feb 2024 and live quotes, but no quote history. Every fill in these
results is therefore *modelled*: a mark from the bar ladder, plus a haircut
of the modelled half-spread. The haircut was swept as a robustness axis
rather than tuned, and it dominates every other knob:

| Fill haircut | Meaning | Spread 0.55Δ, DTE 7–14 |
|---|---|---|
| 0.0 | Fills at mid, always | $40,766 |
| 0.25 | Patient limit orders | $27,379 |
| 0.5 | Default assumption | $19,316 |
| 1.0 | Market orders crossing the quote | **$1,427** |

A debit spread pays the bid-ask **four times** (two legs, in and out); a
long call pays it twice. That asymmetry is invisible at good fills and
decisive at bad ones — at haircut 1.0 every spread configuration tested
loses money while every long call configuration stays profitable.

**Consequence for trading this**: the edge lives in the execution. Patient
limit orders near the mid are not a refinement of this strategy, they are a
precondition. Paper trading is the only real test of the fill model, and it
should be run before any live money.

## The variation sweep (144 configurations)

DTE window × long-leg delta × short-strike placement × fill haircut, every
cell replaying the same 2,565 events. 25.7 hours of wall clock.

**Two families had to be excluded before reading anything.** Configurations
placing the short strike at 2R produced profit factors of 33 and average
returns of 537% of debit — the signature of a collapsing denominator, not an
edge. Diagnosis: a nearer short strike collects more premium, and when one
leg carries a stale or synthetic mark the net debit falls to a few cents on
a $2-wide spread. Position sizing then buys 17 contracts of it and one trade
dominates the aggregate. `DebitSpread` now refuses any debit under 15% of
the spread's width (`debit_implausible`). Verified that the 3R family is
unaffected — its minimum debit was $0.219/share, none below the floor — so
the headline result above stands. The 2R family needs a re-run to be judged.

**Ranking is by profit factor at the worst fill quality**, not by final
equity: equity compounds through a 3-slot portfolio whose composition shifts
with every knob, so a lucky early winner can outweigh the parameter being
tested.

| Configuration | PF @mid | @0.25 | @0.5 | @cross | Trades | Equity @0.5 |
|---|---|---|---|---|---|---|
| DTE 21-35, 0.65Δ long call | 2.33 | 2.10 | 1.75 | **1.32** | 318 | $8,207 |
| DTE 7-14, 0.60Δ long call | 1.97 | 1.75 | 1.57 | **1.20** | 849 | $10,780 |
| DTE 7-14, 0.55Δ long call | 2.00 | 1.76 | 1.55 | **1.19** | 1,021 | $12,083 |
| DTE 7-14, 0.55Δ spread@3R | 2.91 | 2.04 | 1.56 | 0.91 | 1,270 | **$19,316** |
| DTE 14-21, 0.55Δ spread@3R | 2.74 | 1.95 | 1.40 | 0.81 | 1,154 | $9,603 |

Three findings, each consistent across the whole grid rather than resting on
one cell:

1. **Every long call stays profitable per trade at the worst fills; no
   spread does.** The spread crosses the bid-ask four times against the long
   call's two. That asymmetry is invisible at good fills and decisive at bad
   ones.
2. **Lower delta is monotonically better**: 0.55 → 0.60 → 0.65 → 0.70 walks
   the median equity down $10,470 → $9,680 → $7,992 → $4,793. Paying more
   premium for a capped move does not pay.
3. **The original parameters were not the best ones.** ANALYSIS.md proposed
   14-21 DTE at 0.60-0.65Δ; moving to **7-14 DTE at 0.55Δ** doubles the
   result ($19,316 vs $9,603) and takes 10% more trades — cheaper contracts
   clear the $150 budget more often. It also fits Phase 1's measured median
   duration of 2-3 trading days, which the longer window was overpaying for.

### Position sizing

Replaying the trades at larger budgets (`scripts/sizing_study.py`) crosses
two ways of deploying the same capital: bigger positions, or more of them.

| Per position | Slots | Deployed | Return | Max DD |
|---|---|---|---|---|
| $150 | 3 | 15% | +285% | −21% |
| $300 | 3 | 30% | **+576%** | −41% |
| $300 | 10 | 100% | +551% | −87% |
| $500 | 3 | 50% | +987% | −70% |
| $1,000 | 3 | 100% | −104% | ruin |
| $500 | 5 | 83% | −101% | ruin |

Position size drives return; position *count* does not. Ten $300 positions
capture 751 of 772 signals against 401 for three — and return slightly less
(+551% vs +576%) for twice the drawdown. The signals are long-only momentum
on correlated large caps, so ten concurrent positions is much closer to one
big bet than to ten independent ones.

Deployment past roughly 50% is where this stops being survivable. The data
contains a **run of 20 consecutive losing trades**; at 5% of equity per
position that leaves 70% of the account, at 33% it leaves 8%, at 100% it
leaves nothing. Options cannot be held through a drawdown — they expire — so
a long losing run is not a drawdown, it is ruin.

Long options are also **not marginable** (Reg T requires 100% payment under
nine months to expiry), so leverage here can only come from the structure's
delta, never from borrowing.

## Why the pre-2024 extension was abandoned

The plan called for extending the backtest to 2020–2024 with Black-Scholes
marks calibrated on the overlap. The calibration itself succeeded
(`IV ≈ 0.135 + 0.549·RV`, fit on 709 backed-out entry IVs, corr 0.61), and
the synthetic pricer reproduces entries well: 88% identical strike
selection, median debit error under $1, 100% agreement on exit reasons.

It fails on **exit valuation**, biased −15.5% of debit per trade (p10 −45%),
which flips aggregate P&L from +$2,545 real to −$9,441 synthetic on the 622
joined trades. Per the acceptance gate defined before the run, the synthetic
extension is not reported as evidence. Which side is closer to the truth —
a pessimistic model, or stale real prints on illiquid strikes — is another
question only live quotes can settle.

## Known limitations

- Modelled fills, as above. The single biggest uncertainty.
- Free-tier option bars are *indicative* prices, not OPRA.
- Sparse minute bars on illiquid strikes; ~5% of marks are fully synthetic.
- The 80-name universe is a 2026 snapshot; the sub-$150 filter uses
  start-of-backtest prices (20 names would flip on today's prices — recorded
  in `config/universe_sub150.json`).
- Exits are priced at the touched level on the trigger bar. A
  `--next-bar-exit` pessimism flag exists and should be part of any
  pre-live sensitivity pass.

## Reproducing

```bash
set -a; source ~/.secrets/alpaca-thetaforge-competition.env; set +a
uv run python scripts/build_universe.py --start 2020-01-01 --end 2026-08-01
uv run python scripts/run_phase1_underlying.py --label bench30m \
    --start 2020-01-01 --end 2026-08-01 \
    --initial-equity 3000 --max-concurrent 3 --max-position-pct 0.33
uv run python scripts/backtest_overlay.py \
    --events-file reports/phase1/events30m_trades.json \
    --structure all --pricing real --start 2024-02-12 --label real_window
```
