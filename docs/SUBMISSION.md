# Hackathon submission kit

Everything the lablab.ai form asks for, ready to paste. Deadline:
**Friday Sep 4, 10:00 AM CDT.**

## Form fields

| Field | Value |
|---|---|
| Title | `DeltaForge` |
| Cover image | `docs/cover.png` (1920×1080, 16:9) |
| Video presentation | *(record — script below, ≤5 min, ≤300 MB, upload and paste link)* |
| GitHub repository | `https://github.com/jacedeno/deltaforge` |
| Application URL | `https://deltaforge.geekendzone.net` |
| Alpaca paper account ID | `PA3YN2XF0XWT` |
| Technologies | Alpaca Trading API · Alpaca Market Data (options + SIP/IEX stocks) · Python · pandas · Next.js · SQLite · lightweight-charts · ECharts |
| Social links (≤5) | *(paste the X / LinkedIn posts from the week)* |

## Short description (≤255 characters)

> An autonomous options agent on a validated 30-minute momentum signal:
> slightly-ITM calls, closed by the underlying's own stop, 3R target and
> DTE clock. Backtested on real Alpaca options data; +7.25% in four live
> paper sessions on $100k.

## Long description (≥100 words)

> DeltaForge turns a validated momentum signal into an options position an
> autonomous agent can manage. When price closes above its 55-period SMA
> on a 30-minute bar — having been under it the bar before, above the
> 21-SMA, on a bullish candle — the agent buys a slightly-ITM call at
> 7–14 DTE and lets the underlying's own levels close it: the frozen
> 8-bar pivot stop, a 3R target, or a 5-DTE clock.
>
> The edge was measured before it was traded. Over 2,345 backtested trades
> on real Alpaca options data, the target is hit only 13% of the time; the
> edge is the asymmetry at the stop, where a full-R loss in shares costs
> the call about a third of its debit. The repo also documents the version
> that failed: the original debit-spread thesis was killed when
> verification showed its profit rested on five implausible trades.
>
> The agent ran the competition unattended — limit orders at mid, chased
> no further than the haircut the backtest assumed — journaling every
> decision to a public dashboard. It finished +7.25% in four sessions,
> closed to cash for judging, including a measured lesson on protective
> floors that the write-up does not hide.

## Video script (≤5 minutes, one screen-recording take)

Tabs to open, in order: (1) the live dashboard, (2) the GitHub README,
(3) docs/BACKTEST.md, (4) a DELL/NVDA TradeChart expanded on the dashboard.

**0:00–0:35 — the number and the claim.** Dashboard on screen, equity
curve visible.
"This is DeltaForge, an autonomous options trading agent I built during
this hackathon. It traded a $100,000 Alpaca paper account for four
sessions without a single human order — every entry, every exit, every
price you see on this dashboard was the agent's own decision. It finished
at plus seven point two five percent, closed to cash. I want to show you
what it does, and why I trust the number."

**0:35–1:30 — the strategy.** Switch to the README "How it trades" table.
"The signal is a 30-minute momentum cross: price closes above its 55-period
moving average, having been below it the bar before, above the 21, on a
bullish candle. That cross hands the agent three anchors — a direction, a
frozen stop from the last eight bars, and a target at three times the
risk. The instrument is a slightly in-the-money call, one to two weeks
out. The option is just the vehicle: the underlying's own levels close
the trade."

**1:30–2:30 — the evidence.** Scroll to "Where the edge comes from", then
flash BACKTEST.md.
"Before this traded a dollar, I replayed it over two thousand three
hundred trades of real Alpaca options data. The honest finding: the
target is only hit thirteen percent of the time. The edge is at the stop
— a stop that costs shares a full R costs the option about a third of its
debit, and that truncation pays for the tail. The repo also shows the
strategy that died: the original debit-spread thesis failed verification,
and killing it is documented, because a backtest you can't falsify is
marketing."

**2:30–3:40 — the agent and the dashboard.** Back to the dashboard;
expand a trade chart; point at the SMAs, ENTRY candle, levels; show the
trade history with the exit-reason chips.
"The live executor mirrors the backtest bar for bar — same entry logic
imported from the validated repo, same frozen stop, same clock. What the
backtest couldn't model, the agent measures: it works limit orders at
mid and refuses to chase past the slippage the backtest assumed. Every
trade journals to SQLite and renders here — the exact moving averages the
bot computes, the entry candle, the stop and target it is holding, and a
history that includes the trades that never filled."

**3:40–4:40 — the judged week, honestly.** Equity curve, 1W range.
"The week itself: a drawdown on day one, a recovery, and on judging day a
protective floor fired during a six-minute waterfall and closed the book
to cash in four minutes at three hundred dollars of friction. The
uncomfortable part is on the record too — that waterfall was the bottom
of a V, and the floor was calibrated tighter than the book's own measured
volatility. That lesson is now the first study in the queue. Four
sessions can't prove an edge; twenty-eight months of measured trades and
a system that tells the truth about itself are the actual result."

**4:40–5:00 — close.** Cover image or README header.
"DeltaForge — built in six days on Alpaca's trading and options data
APIs, for the Alpaca AI Trading Agents Hackathon with lablab.ai. The
repo, the backtests, and the live dashboard are public. Thank you."

## Recording notes

- One take, screen + voice. Do not edit; a clean single take reads better
  than cuts. If a sentence trips, pause two seconds and repeat it.
- 1080p window, dark theme, close every unrelated tab first.
- The dashboard is public — record against
  https://deltaforge.geekendzone.net, not localhost.
