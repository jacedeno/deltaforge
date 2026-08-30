"""Bull call debit spread anchored to the system's own levels (ANALYSIS.md).

Long call at the strike whose entry-time delta is nearest ``long_delta``
(default 0.625, the 0.60-0.65 band); short call at the listed strike nearest
the 3R target; expiry = the latest Friday inside the DTE window (default
14-21) — the most time the window allows, since the median trade needs to
resolve before theta does the damage.
"""

from __future__ import annotations

from datetime import timedelta

from deltaforge.structures.base import (
    EntryContext,
    Leg,
    Position,
    Skip,
    size_contracts,
)


class DebitSpread:
    name = "debit_spread"

    def __init__(
        self,
        long_delta: float = 0.625,
        dte_min: int = 14,
        dte_max: int = 21,
        short_at_r: float | None = None,  # None = at the event's own target
        min_debit_pct_of_width: float = 0.15,
    ) -> None:
        self.long_delta = long_delta
        self.dte_min = dte_min
        self.dte_max = dte_max
        self.short_at_r = short_at_r
        self.min_debit_pct_of_width = min_debit_pct_of_width

    def select(self, ctx: EntryContext) -> Position | Skip:
        ev = ctx.event
        signal_day = ev.signal_ts.date()
        lo = signal_day + timedelta(days=self.dte_min)
        hi = signal_day + timedelta(days=self.dte_max)
        in_window = [c for c in ctx.contracts if lo <= c.expiry <= hi]
        if not in_window:
            return Skip("no_expiry_in_window", f"{lo}..{hi}")
        expiry = max(c.expiry for c in in_window)
        chain = sorted((c for c in in_window if c.expiry == expiry), key=lambda c: c.strike)
        if not chain:
            return Skip("no_contracts")

        target_price = (
            ev.target
            if self.short_at_r is None
            else ev.entry_price + self.short_at_r * ev.risk_per_share
        )

        candidates = []
        for c in chain:
            d = ctx.entry_delta(c)
            if d is not None:
                candidates.append((abs(d - self.long_delta), c))
        if not candidates:
            return Skip("no_long_strike", "no candidate had a computable delta")
        long_c = min(candidates)[1]

        shorts = [c for c in chain if c.strike > long_c.strike]
        if not shorts:
            return Skip("no_width", f"no strike above long {long_c.strike}")
        short_c = min(shorts, key=lambda c: abs(c.strike - target_price))

        long_mark, short_mark = ctx.mark(long_c.occ), ctx.mark(short_c.occ)
        debit = ctx.fills.buy(long_mark.price) - ctx.fills.sell(short_mark.price)
        if debit <= 0:
            return Skip("negative_debit", f"{debit:.4f}")

        # A debit far below the spread's width means one leg was marked from a
        # stale or synthetic print: the market does not sell a $2-wide ITM
        # spread for $0.09. Such a quote is not tradeable, and because every
        # percentage metric divides by the debit, one of them can dominate a
        # whole run (the 2026-08-29 sweep produced profit factors of 33 and
        # 17-contract positions this way). Reject rather than believe it.
        width = short_c.strike - long_c.strike
        if debit < self.min_debit_pct_of_width * width:
            return Skip(
                "debit_implausible", f"debit {debit:.3f} vs width {width:.2f}"
            )

        n = size_contracts(debit, ctx.max_debit)
        if n < 1:
            return Skip(
                "debit_exceeds_budget", f"debit ${debit * 100:.0f} > budget ${ctx.max_debit:.0f}"
            )

        legs = (
            Leg(long_c.occ, long_c.expiry, long_c.strike, +1, ctx.fills.buy(long_mark.price)),
            Leg(short_c.occ, short_c.expiry, short_c.strike, -1, ctx.fills.sell(short_mark.price)),
        )
        return Position(
            structure=self.name,
            legs=legs,
            contracts=n,
            entry_ts=ev.signal_ts,
            debit_per_share=debit,
            open_fees=ctx.fees.one_way(n_legs=2, n_contracts=n),
        )
