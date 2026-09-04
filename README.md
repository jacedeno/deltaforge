<div align="center">
  <img src="dashboard/public/logo.svg" width="96" alt="The DeltaForge mark — a faceted delta with a strike line">
  <h1>DeltaForge</h1>
  <p><em>A directional options overlay on a validated momentum signal.<br>
  The signal picks the direction; the option shapes the payoff.</em></p>
  <p>
    <a href="https://deltaforge.geekendzone.net"><b>Live dashboard</b></a> ·
    <a href="docs/ANALYSIS.md">Strategy analysis</a> ·
    <a href="docs/BACKTEST.md">Backtest report</a> ·
    <a href="docs/DEPLOYMENT.md">Operations</a>
  </p>
</div>

---

**Status: traded on paper 2026-08-31 → 2026-09-03, closed to cash at +7.25%
for judging.** One autonomous bot against one
account — Alpaca paper **`PA3YN2XF0XWT`** (the competition account), $100,000,
$7,000 a position across 14 slots — opening every position itself and narrating
what it did on the [dashboard](https://deltaforge.geekendzone.net). Built for
the [Alpaca AI Trading Agents Hackathon](https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon);
the first commit landed four hours after kickoff.

![The dashboard at the judged close: equity $107,247.11, up $7,247.11 since
inception, zero open positions, and the week's equity curve](docs/images/dashboard-equity-curve.png)

<sub>The judged week, closed to cash: <b>+$7,247.11 on $100,000</b>, no
position left open. The curve is the whole record — the day-one drawdown,
the recovery, and the flat line after the book was closed.</sub>

## How it trades

The ML30 momentum signal fires when, on a single 30-minute candle close,
price crosses above its 55-period SMA from below, sits above the 21-period
SMA, and the candle itself is bullish. That cross hands the overlay three
anchors:

| Anchor | Rule | Role |
|---|---|---|
| **Direction** | long, at the cross bar's close | what to buy |
| **Stop** | lowest low of the 8 bars before entry, frozen | when the thesis is wrong |
| **Target** | entry + 3× the stop distance | how far "right" is worth riding |

The instrument is a **slightly-ITM call, 0.55 delta, 7–14 DTE**, sized at
$7,000 a position. The underlying's own levels close the trade — stop touch,
target touch, or a DTE clock at 5 days to expiry — and signals whose 3R
target sits under 5% away are refused, because a short walk cannot pay for
an option's bid-ask and theta.

![NVDA on 30-minute bars: the 21 and 55 SMAs, the entry candle marked at the
cross, and the frozen stop and 3R target the agent is holding](docs/images/trade-chart-nvda.png)

<sub>The three anchors, as the dashboard draws them: the cross that fired the
entry, the 8-bar pivot stop below it, and the 3R target above. The chart
renders the same moving averages the bot computes — not a reconstruction.</sub>

## Where the edge comes from

Not from hitting targets. Measured over 2,345 backtested trades at the live
configuration, the 3R target is touched **13%** of the time. The edge is the
asymmetry at the stop:

```
52% of trades stop out   →  −36.8% of debit on average   (shares would lose a full R)
13% reach the target     →  +119.7% of debit on average
34% exit on the clock    →  whatever the move gave
─────────────────────────────────────────────────────────
expectancy               →  +9.9% of debit per trade
```

A long call cannot lose more than was paid for it, and still carries time
value when the underlying touches the stop. Truncating the losses that way —
while leaving the right tail open — is the entire trade. The signal supplies
direction slightly better than chance; the option structure turns that small
edge into a payoff worth having.

Over the full replay window (Feb 2024 → Aug 2026, real Alpaca options data,
identical signal events), the same rules on a $3,000 account turn it into
**$12,130 (+304%)** against **+66%** for the underlying shares. At the live
$100,000 configuration the replay compounds further and draws down harder
(−56% at the worst); the budget ladder in `reports/budget_100k_v2/` shows the
per-trade edge is identical at every position size tested — what sizing
buys, and costs, is concentration.

## Why one week undersells it

An honest note for hackathon judges: this strategy's weakest possible
showcase is a handful of sessions, and that is what a one-week competition
measures.

- **The window is shorter than one trade's life.** Median hold is 3.8 days
  and exits arrive on a 5–9 day DTE clock. The book's first positions were
  opened Sep 1; their scheduled exits land *after* the judged close.
- **The book needs over a week to reach steady state.** It fills at roughly
  four positions a day from flat. The judged equity catches it mid-ramp.
- **The edge lives in the right tail.** At a 36.8% win rate, expectancy
  emerges over hundreds of trades. Eight trades in, variance is the only
  thing visible — in either direction.
- **End-of-day marks understate a long-options book.** Alpaca marks long
  options at the bid; at the 2026-09-02 close the gap between marked equity
  and the quoted mids on this account was **$5,165** — about 5% of the
  account, on spreads as wide as 117% in the closing print.
- **The regime is thin.** Current volatility sits near the bottom of the
  2020–2026 distribution, so signals are few and narrow — documented in the
  backtest report before the event began. Few trades is the filter working.

![Six open long calls — UAL, INTC, NVDA, DELL, MS, UNH — with their debit,
live bid/ask, days left and P&L](docs/images/dashboard-open-positions.png)

<sub>The book mid-ramp: six of fourteen slots filled, winners and losers
side by side. This is what a one-week window actually measures.</sub>

The 30-month record above, the falsification work below, and a live journal
that matches the backtest's mechanics bar for bar are the useful evidence.
Three sessions of P&L — good or bad — are not.

## What did not survive

The repo's original thesis was a bull call **debit spread** with its short
strike at the 3R target — the literal translation of the system into
options. Verification killed it: its apparent +286% rested on 5 trades out
of 772 and on a cohort of implausibly cheap spreads that contributed more
than all of the profit. The long call replaced it. The full post-mortem is
in ["What did not survive"](docs/BACKTEST.md) — kept public because the
discard is the strongest evidence the rest of the numbers were checked with
the same suspicion.

## What is in the repo

```
src/deltaforge/        backtest engine — hybrid pricing ladder
                       (real minute prints → BS anchored to observed IV → BS),
                       structures, per-trade lifecycle, portfolio replay
src/deltaforge/live/   the bot — contract selector, broker, executor, journal
src/deltaforge/ml30/   the ML30 signal code the bot runs on, vendored (entry,
                       indicators, pivot stop, Alpaca historical client)
dashboard/             Next.js dashboard: candles with the strategy's own SMAs
                       and levels, anchored VWAPs, equity curve, trade journal
scripts/               phase 1–3 pipelines, the bot entrypoint, universe builders
docs/                  ANALYSIS.md · BACKTEST.md · DEPLOYMENT.md
reports/               every artifact the docs cite, reproducible from the CLI
config/                trading universes and IV calibration
```

The live executor mirrors the backtest's mechanics exactly — the same entry
logic the backtests ran, vendored rather than reimplemented, same
frozen stop, same-bar precedence, same DTE clock — because any divergence
would make the paper phase measure something other than what was tested.
What the backtest could not model and the bot must, it measures: limit
orders at mid, chased no further than the haircut the backtest assumed,
abandoned rather than crossed.

![A closed DELL trade: contract DELL260911C00467500, delta at entry 0.542,
asked 21.68 filled 21.50, exit filled 42.55, debit $6,450, fees $3.90, and
the two fills with their timestamps](docs/images/trade-detail-dell.png)

<sub>What the journal keeps for every position: the contract, the delta it
was chosen at, what was asked versus what filled on both legs, the fees,
the three levels, and the fill log. This one closed at <b>+$6,311.10</b>.
Its exit is tagged <code>MANUAL</code> because the judging-day protective
floor (<code>scripts/bracket_watch.sh</code>) closed it, not one of the bot's
three mechanical exits — the journal keeps the two apart.</sub>

## Run it

```bash
export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...   # historical SIP entitlement needed
uv run python scripts/run_phase1_underlying.py --help   # phase 1: signal on shares
uv run python scripts/backtest_overlay.py --help        # phase 2: options overlay
uv run python scripts/sweep_overlay.py --help           # phase 3: variations
uv run python scripts/run_paper_bot.py --help           # the bot itself
```

## Pre-event work disclosure

The ML30 signal this overlay trades — the 21/55 cross on 30-minute bars, the
8-bar pivot stop, the 3R target — comes from the author's prior research and
a separate production system that predates the event. The exact modules the
bot calls are vendored in `src/deltaforge/ml30/` (pinned to that system's
commit `c7ad990`, 2026-09-02) so this repository runs on its own. Everything in this
repository — the overlay analysis, the backtest engine, the paper bot and
the dashboard — was designed, built and shipped inside the hackathon window
(first commit 2026-08-28 14:41 CDT), and the account it trades was opened
new during the event with the required $100,000 starting balance.

## About the author

**Jose Cedeño** · [github.com/jacedeno](https://github.com/jacedeno) ·
joseangel.cedeno@gmail.com

I run a small fleet of automated trading systems out of a self-hosted
homelab: a real-money ML30 momentum bot and DeltaForge. The signal
research, the backtesting practice and the infrastructure underneath —
from the Proxmox cluster and its failover to the dashboards on top — are
built and operated end to end by me.

## Disclaimer

Paper trading, simulated funds, real market data. Nothing here is
investment advice; the backtest report is explicit about its assumptions
and their limits, and going live is gated on evidence the paper phase has
not yet produced.
