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

## What did not survive verification

**Read this before the tables below.** The first pass of this document led
with the debit spread returning +286% against the underlying's +66%, and
recommended moving to 7–14 DTE. Re-running the winning configuration through
a control run exposed both claims as artifacts. The tables further down are
kept as recorded, with this section as their correction.

Three independent checks, each of which the spread fails and the long call
passes:

| Check | Spread (14–21 DTE) | Long call (7–14 DTE, 0.55Δ) |
|---|---|---|
| P&L without its 5 best trades | **−$213** (loses) | +$11,791 of $16,217 |
| Trades with debit < 15% of spread width | 29 trades = **122% of P&L** | n/a (single leg) |
| P&L from real prints vs model marks | 85% from model-marked | **114% from real prints**; model-marked cohort *loses* $2,278 |

The mechanism: when one leg of a spread is marked by Black-Scholes instead
of an actual trade, the *net* debit of the two legs can come out
implausibly small — cents on a $2-wide spread. Every percentage metric then
divides by that tiny debit, and position sizing buys up to 24 contracts of
it. A handful of such trades carried the entire result. `DebitSpread` now
rejects any debit under 15% of width (`debit_implausible`); with that guard
the same configuration that scored $19,316 in the sweep returns **$955 with
a profit factor of 0.96** — it loses money.

The long call inverts every one of these signals. It has no second leg for a
net debit to collapse through; its profit is distributed across 1,000 trades
rather than concentrated in a handful; and the trades priced entirely from
real prints are the profitable ones, while the model-marked cohort loses
money. That is the opposite of what a pricing artifact looks like.

**Resolved since:** `LongCall` now refuses any premium whose time value is
under 0.3% of spot (`premium_implausible`), the single-leg analogue of the
width test. It rejected 37 contracts, and the result barely moved — 982
trades at PF 1.50 against 1,000 at PF 1.54, equity $11,305 against $12,130.
That is the difference between a guard that removes noise and one that
removes the result: the same guard applied to the spread took it from
$19,316 to $955.

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

Swept on the final configuration ($300, 7–14 DTE, 0.55Δ, both guards), the
whole result lives on this line:

| Fills | Trades | PF | Avg P&L | Equity | Max DD |
|---|---|---|---|---|---|
| Exact mid | 1,617 | 1.86 | +17.9% | $20,693 | −28% |
| Patient limit | 1,597 | 1.65 | +14.2% | $18,875 | −33% |
| Base assumption | 1,591 | 1.45 | +10.5% | $15,168 | −32% |
| Crossing the spread | 1,564 | 1.15 | +3.8% | $5,598 | −44% |

Two things to take from it. The strategy survives even the worst execution —
profit factor 1.15, $3,000 to $5,598 — which is more than the debit spread
managed at *any* fill quality. And the spread between best and worst
execution is nearly four times the ending account, on identical signals and
identical contracts. **Which row you land on is not a modelling question, it
is an execution question**, and it is the one thing paper trading is for.

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

### Budget: how much per position

Three full pipeline runs with both plausibility guards in place, the $150 run
doubling as a control against the sweep. The debit cap was throttling the
signal stream:

| Budget | Signals traded | Skipped on budget | PF | Equity | Max DD | P&L without top 10 |
|---|---|---|---|---|---|---|
| $150 | 982 | 1,364 | 1.50 | $11,305 | −23% | $7,838 |
| $300 | 1,591 | 755 | 1.45 | **$15,168** | −32% | $27,957 |
| $500 | 1,918 | 428 | 1.43 | $12,664 | −40% | $56,778 |

Per-trade edge is flat across budgets (PF 1.43–1.50), so the budget is not
buying a better strategy, it is buying access to more of the same one. The
gross edge keeps growing with it — the P&L surviving removal of the ten best
trades rises from $8k to $57k — while portfolio equity peaks at $300, because
a three-slot account cannot harvest the larger edge without also taking the
larger drawdowns.

### It works in the year the shares strategy does not

Splitting the $300 run by calendar year answers the question that matters for
deploying now rather than in hindsight:

| Year | Trades | Win rate | PF | P&L |
|---|---|---|---|---|
| 2024 | 680 | 36% | 1.37 | $15,820 |
| 2025 | 586 | 39% | 1.65 | $20,732 |
| **2026** | **325** | **33%** | **1.31** | **$6,395** |

2026 is the *only losing year* for the underlying shares strategy (PF 0.82,
−0.14 R — the flat live account that started this investigation), and the
overlay is comfortably profitable in it. The mechanism is the asymmetry
already measured: a stop in shares costs a full R, a stop in the long call
costs roughly a third of the debit. In a chopping year that gets stopped out
often, truncating the loss is worth more than the leverage.

### The filter the strategy was missing

Bucketing the $300 run by how far the 3R target sits from entry separates the
result almost completely:

| Target distance | Trades | Win rate | Avg P&L | Total P&L |
|---|---|---|---|---|
| 0–2% | 99 | 39% | +3.1% | $596 |
| 2–3% | 229 | 33% | +1.3% | $511 |
| 3–5% | 532 | 33% | +0.6% | $737 |
| **5–8%** | 425 | 41% | **+19.2%** | **$19,986** |
| **8%+** | 306 | 38% | **+24.8%** | **$21,116** |

The 860 signals under 5% — **54% of all trades** — returned $1,844 of roughly
$42,000, about 4% of the profit. They are not merely weaker; they are close
to free, and they carry the drawdown of a full position each.

Requiring the target to sit at least 5% away:

| Minimum target | Trades | Equity | Return | Max DD |
|---|---|---|---|---|
| none | 1,591 | $40,908 | +1,264% | −38% |
| ≥3% | 1,263 | $41,143 | +1,271% | −28% |
| ≥4% | 993 | $43,348 | +1,345% | −26% |
| **≥5%** | **731** | **$43,860** | **+1,362%** | **−20%** |
| ≥6% | 536 | $33,388 | +1,013% | −17% |

Less than half the trades, a slightly higher return, and **half the
drawdown**. The gradient is smooth to 5% and breaks at 6%, where too few
signals remain — the shape of a real effect rather than a fitted number.

It is also not a new idea. ANALYSIS.md ruled out the 5-minute variant because
its 1–2% target distances cannot cover an option's bid-ask and theta, and
expected 3–6% from the 30-minute levels. This filter simply enforces the
premise the strategy was designed on, instead of assuming every 30-minute
signal satisfies it. Roughly half do not.

**Live consequence, felt immediately.** The first dry run against the market
of 2026-08-28 produced two signals, at 1.77% and 1.14% — both inside the band
that does not pay, both refused. Median 3R distance across the universe over
the preceding month runs 1.6–4.4%, against the 5.57% median of the full
2020–2026 sample. The current regime sits near the bottom of the historical
volatility distribution, so a correctly-behaving bot will trade rarely until
that changes. Few trades is the signal working, not the bot failing.

### Position sizing: grow the count, not the bet

**This section has been wrong twice.** Its first version was computed on the
debit-spread trades and died with them. Its second concluded that fixed-
fractional sizing was safer because it shrinks positions during a drawdown —
true in isolation, and swamped by an effect it ignored.

Two policies, both reaching 100% deployment, differing only in where growth
goes:

| Policy | Equity | Return | Max DD | Trades |
|---|---|---|---|---|
| 10% of equity per position, 10 slots | $216,032 | +7,101% | **−76%** | 1,384 |
| **$300 fixed, one more slot per $300 of growth** | $46,372 | +1,446% | **−38%** | 1,583 |
| 10% of equity, no liquidity ceiling | $563,213 | +18,674% | −96% | 1,382 |

**At $3,000 the two are the same thing** — 10% of equity is $300, ten
positions either way. They diverge only as the account moves, and then
sharply: compounding the *bet* compounds the risk with it, so the
fixed-fractional path reaches a higher peak and gives back three quarters of
it. The fixed-dollar path takes more trades, halves the drawdown, and keeps a
return that is still far beyond the underlying.

Each policy also fails differently at scale, which decides it. Fixed-dollar
runs into signal availability — roughly 1.6 signals a day means there is no
fortieth concurrent position to open, so it stops scaling on its own. Fixed-
fractional runs into liquidity: $3,000 into one weekly option on a mid-cap
name is not a fill, and the third row above shows what the model prints when
nothing stops it. The first wall is free to discover; the second is expensive.

Slot count within the tradeable range barely matters. From 6 to 12 concurrent
positions the outcome sits between $35k and $44k; 8 slots gives −34% drawdown
and 10 gives −38%. Being above roughly five slots is what counts.

Long options are **not marginable** (Reg T requires payment in full under nine
months to expiry), so leverage here comes from the structure's delta and never
from borrowing. Rows implying more than 100% deployment are arithmetic, not
plans.

## The short side does not have an edge

The overlay is long-only because every signal ever backtested was long. The
obvious way to roughly double the trade count is to mirror the signal, which
ml30 supports natively (`Coordinator(direction=Direction.SHORT)`, an exact
mirror of the entry, stop and 3R bracket). Run over the same universe,
window and parameters as Phase 1:

| | Long | Short |
|---|---|---|
| Closed trades | 6,724 | 7,104 |
| Expectancy | **+0.162 R** | **−0.060 R** |
| Profit factor | **1.229** | **0.921** |
| At −1.3R stop fills | −0.050 R / 0.945 | −0.290 R / 0.709 |
| Target-touch rate | 29.1% | 23.5% |
| Median duration | 3 days | 2 days |
| $3,000 portfolio, 3 slots | **$18,788 (+526%)** | **$1,228 (−59%)** |
| Max drawdown | 23.1% | **69.8%** |

It is negative in six of seven years; the exception is 2022, the bear
market. That is the whole story — a mirrored trend-following entry on a
universe of large caps in a market that rose over the period.

**The one argument for building it anyway, and why it loses.** Phase 1's
gate is expectancy on the underlying, but the overlay does not inherit the
underlying's payoff: measured on the ≥5% long trades, a stop costs the
option **−17.9% of debit** where shares lose a full R, and a target pays
**+112.2%**. That truncation can rescue a signal shares cannot trade.
Applying the same two multipliers to the short stream's exit mix (21.9%
target / 78.1% stop) projects **+10.5% of debit per trade**, against
+23.5% for the long.

Positive — but less than half the long's edge, and resting on the
assumption that puts behave like calls. They do not: put skew makes
downside strikes systematically richer, which comes straight out of that
+10.5%. Building put structures and running the full pipeline to chase
half the edge, on a signal whose underlying loses money in six years of
seven, is not where the next week goes. Revisit only if the live long
book shows the truncation effect running stronger than modelled.

Reproduce with `--direction short` (artifacts: `events30m_short_*`,
`bench30m_short_*`).

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
export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...   # SIP-entitled keys
uv run python scripts/build_universe.py --start 2020-01-01 --end 2026-08-01
uv run python scripts/run_phase1_underlying.py --label bench30m \
    --start 2020-01-01 --end 2026-08-01 \
    --initial-equity 3000 --max-concurrent 3 --max-position-pct 0.33
uv run python scripts/backtest_overlay.py \
    --events-file reports/phase1/events30m_trades.json \
    --structure all --pricing real --start 2024-02-12 --label real_window
```
