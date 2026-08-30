"""Slightly-ITM long call (ANALYSIS.md's exception-case alternative).

65-70 delta, 21-28 DTE. In sweeps this is also what a debit spread with no
short leg degenerates to, which is how the "was the short call worth it?"
question gets answered on identical events.
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


class LongCall:
    name = "long_call"

    def __init__(
        self,
        delta: float = 0.675,
        dte_min: int = 21,
        dte_max: int = 28,
        min_time_value_pct_of_spot: float = 0.003,
    ) -> None:
        self.delta = delta
        self.dte_min = dte_min
        self.dte_max = dte_max
        self.min_time_value_pct_of_spot = min_time_value_pct_of_spot

    def select(self, ctx: EntryContext) -> Position | Skip:
        ev = ctx.event
        signal_day = ev.signal_ts.date()
        lo = signal_day + timedelta(days=self.dte_min)
        hi = signal_day + timedelta(days=self.dte_max)
        in_window = [c for c in ctx.contracts if lo <= c.expiry <= hi]
        if not in_window:
            return Skip("no_expiry_in_window", f"{lo}..{hi}")
        expiry = max(c.expiry for c in in_window)
        chain = [c for c in in_window if c.expiry == expiry]

        candidates = []
        for c in chain:
            d = ctx.entry_delta(c)
            if d is not None:
                candidates.append((abs(d - self.delta), c))
        if not candidates:
            return Skip("no_long_strike", "no candidate had a computable delta")
        long_c = min(candidates)[1]

        mark = ctx.mark(long_c.occ)
        debit = ctx.fills.buy(mark.price)
        if debit <= 0:
            return Skip("negative_debit", f"{debit:.4f}")

        # A spread catches a stale mark by comparing the two legs; a single
        # leg has nothing to compare against, so check the premium against
        # the underlying instead. A call near 0.55 delta with days left to
        # run carries real time value — a few cents on a $40 name is a stale
        # print, and sizing would buy 70 contracts of it.
        intrinsic = max(ctx.spot - long_c.strike, 0.0)
        time_value = mark.price - intrinsic
        floor = self.min_time_value_pct_of_spot * ctx.spot
        if time_value < floor:
            return Skip(
                "premium_implausible",
                f"time value {time_value:.3f} < {floor:.3f} (spot {ctx.spot:.2f})",
            )

        n = size_contracts(debit, ctx.max_debit)
        if n < 1:
            return Skip(
                "debit_exceeds_budget", f"debit ${debit * 100:.0f} > budget ${ctx.max_debit:.0f}"
            )

        legs = (Leg(long_c.occ, long_c.expiry, long_c.strike, +1, ctx.fills.buy(mark.price)),)
        return Position(
            structure=self.name,
            legs=legs,
            contracts=n,
            entry_ts=ev.signal_ts,
            debit_per_share=debit,
            open_fees=ctx.fees.one_way(n_legs=1, n_contracts=n),
        )
