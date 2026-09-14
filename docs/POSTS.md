# Public posts from the hackathon week

What was said about DeltaForge in public, and what was answered. Kept here
because the submission form asks for social links, and because the lablab.ai
replies are the only outside reading of the project so far. The first two posts went
out on LinkedIn on 2026-09-08, the Monday after judging; the third on
2026-09-14, when the certificate arrived.

## 1. Wrap-up post

> The Alpaca AI Trading Agents Hackathon just wrapped up, and it was a good
> week.
>
> Thank you Alpaca and lablab.ai for putting on events like this. A real
> paper-trading API, an options data feed, and a one-week deadline force you
> to decide fast, build, and see what happens when the market opens.
>
> My entry was DeltaForge: an autonomous bot that runs a momentum signal on
> 30-minute candles and expresses the direction with call options instead of
> shares. It opened every position on its own all week and closed to cash for
> judging.
>
> As always, the learning is the real prize. Next up, two fronts: improving
> the bot with what I saw live, and building a dashboard to track this bot
> and the others I have coming.
>
> Live dashboard: https://deltaforge.geekendzone.net
> Repo: https://github.com/jacedeno/deltaforge

151 impressions in the first three hours.

**lablab.ai (official account) replied:**

> Running a full week autonomously and closing clean to cash for judging
> shows the bot was actually trusted to operate without a safety net the
> whole time.
>
> Love the framing on expressing a momentum signal through calls instead of
> shares too - same directional thesis, different risk/reward shape. "The
> learning is the real prize" is the right takeaway, and having a dashboard
> planned for tracking this bot alongside future ones is a smart next move
> for comparing strategies over time. Good week!

**Answer posted:**

> Thanks, team. Five sessions of live option orders with zero manual
> overrides taught me more about fills and spreads than any backtest.
> Dashboard next, and I'll be watching the upcoming hackathons. Great week,
> thanks to you and Alpaca.

## 2. DELL and NVDA trade post

> $DELL and $NVDA, two of the trades my bot took during the Alpaca AI
> Trading Agents Hackathon with lablab.ai.
>
> 30-minute bars, same rules on both: entry on the candle that closed above
> the 55-period SMA, stop at the low of the prior 8 bars, target at 3R. Long
> a slightly in-the-money call, with the exit rules living on the stock's
> chart, not the option's price.
>
> Same setup, two names, no discretion in between. That is the whole point
> of writing the rules down.
>
> One honest note: DELL shows a MANUAL exit because I flattened the book on
> judging day. The journal tags that separately from the bot's own three
> exits.
>
> Every trade the bot took: https://deltaforge.geekendzone.net
>
> The multi-timeframe framework behind it owes a lot to Brian Shannon, CMT
> and his work at Alphatrends.net on trend alignment and anchored VWAP.
> Thank you, Brian.

Two chart images attached: the DELL and NVDA trades on the dashboard's
30-minute chart with the SMAs, the frozen stop and the 3R target drawn.

**lablab.ai (official account) replied:**

> "Same setup, two names, no discretion in between. That is the whole point
> of writing the rules down." - exactly the discipline that separates a
> systematic strategy from vibes-based trading dressed up in code.
>
> Tagging the DELL manual exit separately from the bot's own exits is a
> small but important honesty check - keeps the journal clean for anyone
> actually evaluating the strategy's real performance versus your own
> intervention. Nice nod to Brian Shannon's trend-alignment framework too,
> good to see the theoretical foundation credited. Solid, disciplined build.

**Answer posted** (the drafted text; the posted reply follows it closely):

> Thanks. The MANUAL tag exists because the first question anyone should
> ask about a bot's track record is "how much of this was the bot?" If the
> journal can't answer that, the numbers are decoration. Next step is
> putting those exit types side by side on the dashboard so the split is
> visible at a glance, not buried in a table.

## 3. Certificate post (2026-09-14)

Posted the Monday after lablab.ai emailed the participation certificate
(the certificate lives on the lablab.ai profile page). Winners had not been
announced yet.

> Certificate in hand for the Alpaca AI Trading Agents Hackathon with
> lablab.ai.
>
> I am not posting it for the paper. I am posting it because of what it
> took to earn it.
>
> For a long time I had a strategy idea and a dashboard sitting
> half-finished on my list, the kind of project you keep promising yourself
> you will close "when there is time." The hackathon gave me a deadline and
> no excuses. In three days the strategy went from notes to an autonomous
> bot placing real option orders on a paper account, and the dashboard I
> had wanted for months was finally live, journaling every decision the bot
> made.
>
> No prizes here, and honestly that is fine. The win was finishing.
> Watching something you designed run on its own through five market
> sessions, without you touching it, is a feeling I would recommend to
> anyone who builds.
>
> Thank you Alpaca and lablab.ai for the push. Sometimes a deadline is the
> best mentor.
>
> What the bot did, trade by trade: https://deltaforge.geekendzone.net
> Code: https://github.com/jacedeno/deltaforge

Certificate image attached.

## What the replies confirm

Three things the project leaned on were the three things an outside reader
picked up unprompted: the bot ran unattended for the whole week, the
options expression is a deliberate change of risk shape rather than a
gimmick, and the `MANUAL` tag in the journal is an honesty device. Those are
the points to keep front and centre in the README and in any follow-up.

One commitment made in public, now owed: the dashboard should show the
split between mechanical and manual exits at a glance.
