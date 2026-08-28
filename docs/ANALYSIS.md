# Options Overlay for the ML30 Signal on a $3,000 Account

> Analysis, 2026-08-28. Decision support for manual trading in a small real
> account. Nothing here is implemented or backtested yet — see Roadmap in
> the README.

## What the signal gives us

The ML30 system (SMA55/21, four-condition momentum cross, sweep-validated)
produces, at every signal, three concrete numbers an options structure can
be anchored to:

1. **Direction** — long only (fresh cross above SMA55, confirmed above
   SMA21, bullish bar).
2. **A stop price** — the frozen low of the 8 bars before the signal bar.
3. **A target price** — entry + 3R, where R = entry − stop.

The stop and target being *prices*, not vibes, is what makes an options
translation possible: strikes can be placed on them.

## The regulatory ground (why $3k is even viable)

FINRA's June 2026 intraday margin rule replaced the Pattern Day Trader
framework: the $25,000 day-trading minimum and the 3-trades-per-5-days cap
are gone; the standard $2,000 Reg T minimum applies. A $3,000 account can
enter on a signal and exit on a same-day stop without trade-count
restrictions. (Any guide still citing "$25k PDT" predates June 2026.)

## The timeframe finding (this changes everything)

**The 5-minute variant's levels are unusable for options.** On 5-minute
bars the entry→3R distance is roughly 1–2% of the underlying's price. No
strike structure captures a move that small: the bid-ask spread plus
per-contract fees consume the entire edge, and most chains don't offer
strikes spaced tightly enough.

**The 30-minute levels (the screener's) or daily levels are the right
feed.** There the 3R distance runs ~3–6% — wide enough to place a short
strike meaningfully above the entry and leave room for the structure to
pay. The 30-minute screener already computes entry/stop/target per
candidate, which makes it the natural signal source for manual execution.

## Strategies evaluated

### 1. Bull call debit spread anchored to the system's levels — RECOMMENDED

Buy a call near the signal price (60–65Δ), sell the call at the strike
nearest the **3R target**, 14–21 DTE.

Why it is the best mapping:

- The validated system exits at 3R and never captures more. The upside a
  short call gives away is upside the strategy never earns anyway — so the
  cap costs nothing in expectancy and the short leg finances the theta.
- Defined risk = the debit paid. No margin, no assignment surprises worth
  fearing at this size (close before expiration week).
- Exits translate directly: target touched → close at max-profit zone;
  stop price touched → close the spread (typically −40 to −60% of the
  debit, not −100%); 5 DTE reached → close whatever remains.

Sizing at $3,000: on $40–150 underlyings a $3–5-wide spread costs roughly
$120–200. Risk 4–5% per position ($120–150), **2–3 concurrent positions
maximum**. Payoff at target: ~1.5–2.5× the debit.

### 2. Slightly-ITM long call (65–70Δ, 3–4 weeks) — for the cleanest signals

The purest expression of the momentum thesis: uncapped upside, gamma
working with the trend. Costs: theta bleeds while a cross consolidates,
and post-breakout IV crush hurts even correct directional calls. On $3k
the premium restricts the universe to underlyings under ~$100. Use as the
exception for the calmest, strongest signals — not as the base structure.

### 3. Put credit spreads (the ThetaForge structure) — NO at this size

ThetaForge's edge is the law of large numbers: many small premiums across
15 concurrent positions. At $3,000 that becomes 2–3 slots of $1-wide
spreads collecting $10–20 credits, where round-trip fees (~$2.60) are
15–25% of the credit and $1-wide strikes are illiquid on many names. The
math that works at $100k does not scale down to $3k.

### 4. Cash-secured puts — NO

$3,000 secures 100 shares only below a $30 stock. It collapses the
universe to a handful of names and ties the whole account to one position.

## The playbook (to be validated before going live)

1. Signal source: the 30-minute screener's **just-crossed** list, with its
   computed entry / stop (8-bar low) / target (3R).
2. Structure: bull call debit spread, long leg 60–65Δ, short leg at the
   strike nearest the 3R target, 14–21 DTE.
3. Size: $120–150 max debit per position (4–5% of account), 2–3 open
   positions maximum, one per underlying, one per sector when possible.
4. Exit rules, first touch wins: underlying touches the 3R target →
   close · underlying touches the stop price → close · 5 DTE → close.
   No trailing, no averaging down, no rolling.
5. Universe: the sub-$150 half of the 80-name liquid universe (BAC, NKE,
   F, UBER, KO, CSCO, WMT, PFE, MRK, INTC, …) — options liquid, spreads
   affordable.

## Honest caveats

- Fees are a real tax at this size: ~$2.60 per spread round trip is ~2% of
  a $130 debit. The playbook must clear that hurdle in the backtest.
- The 30-minute variant of the signal is itself not yet backtested (the
  sweep validated 5m and 15m). Two stacked unvalidated layers — the 30m
  signal and the options overlay — is exactly why the roadmap demands a
  backtest and a paper period before real money.
- Stops on the underlying do not map linearly to the spread's value; the
  −40 to −60% loss estimate at the stop needs measuring, not assuming.
