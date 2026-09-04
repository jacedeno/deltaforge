# Hackathon submission kit

Everything the lablab.ai form asks for, ready to paste. Deadline:
**Friday Sep 4, 10:00 AM CDT.**

## Form fields

| Field | Value |
|---|---|
| Title | `DeltaForge` |
| Cover image | `docs/cover.png` (1920×1080, 16:9) |
| Video presentation | `~/Videos/deltaforge/deltaforge-submission.mp4` — 3:09, 15 MB, 1600×1194 H.264/AAC *(upload, paste link)* |
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
> The agent opened every position itself — limit orders at mid, chased
> no further than the haircut the backtest assumed — journaling every
> decision to a public dashboard. It finished +7.25% in four sessions,
> closed to cash on judging day by a coded protective floor, including a
> measured lesson on that floor's calibration that the write-up does not
> hide.

## Video (3:09) — as delivered

Narrated by TTS (`edge-tts`, voice `en-US-AndrewNeural`, rate −4%) over a
silent GNOME screen recording, so no spoken English and no video editing
were needed. Two audio tracks were built with identical timing: a *guide*
track with a spoken "Cambio." at every transition, listened to on
headphones while recording, and a *final* track with silence in those
gaps, muxed onto the recording with one `ffmpeg` command. Two tabs, seven
scene changes.

| Cue | On screen | Narration |
|---|---|---|
| **0:00** | Dashboard — equity cards and the 1W curve | You're looking at the live dashboard of DeltaForge, an autonomous options trading agent I built for the Alpaca AI Trading Agents Hackathon. The number on the left is the account: one hundred and seven thousand dollars, up seven point two five percent, on a one hundred thousand dollar Alpaca paper account, over four sessions, closed to cash. Every entry, and every mechanical exit, was the agent's own decision. |
| **0:27** | README — the *How it trades* anchors table | This is the repository, and the table on screen is the whole strategy. The signal is a thirty-minute momentum cross: price closes above its fifty-five period moving average, having been below it the bar before, above the twenty-one, on a bullish candle. That cross hands the agent three anchors. A direction. A frozen stop, taken from the last eight bars. And a target at three times that risk. The instrument is a slightly in-the-money call, one to two weeks out. The option is only the vehicle: the underlying's own levels close the trade. |
| **1:04** | README — scroll to *Where the edge comes from* | Scrolling down, this block is where the edge actually comes from, and it is not where people expect. Over two thousand three hundred and forty-five backtested trades, on real Alpaca options data, the target is hit only thirteen percent of the time. Fifty-two percent stop out. The edge is the asymmetry at that stop: a move that would cost shares a full R costs the option only about a third of its debit. Truncating the loss while leaving the right tail open is the entire trade. |
| **1:35** | README — scroll to *What did not survive* | This next section is the one I would keep if I could keep only one. The original thesis of this repo was a debit spread, and verification killed it. Its apparent gain rested on five trades out of seven hundred and seventy-two. I left the post-mortem public, because a backtest you cannot falsify is marketing. |
| **1:56** | Dashboard — expand the NVDA trade chart | Back on the dashboard, let's open one position. This is the NVIDIA trade. You can see the two moving averages the bot itself computes, the entry candle where the cross fired, and the two levels it is holding: the frozen stop below, and the three R target above. Underneath are the contract, the delta it was chosen at, what was asked, and what actually filled. The agent works limit orders at mid, and refuses to chase past the slippage the backtest assumed. |
| **2:26** | Dashboard — the equity curve, 1W | And this is the judged week, honestly. A drawdown on day one, a recovery, and on the final day a protective floor that closed the book to cash. That floor was calibrated tighter than the book's own measured volatility, and it fired at the bottom of a V. That lesson is on the record too, written into the repo. |
| **2:48** | README — back to the header and logo | Four sessions cannot prove an edge. Twenty-eight months of measured trades, and a system that tells the truth about itself, are the actual result. DeltaForge. Built in six days on Alpaca's trading and options data APIs. The repository, the backtests, and the live dashboard are all public. Thank you. |
| **3:08** | End | |
