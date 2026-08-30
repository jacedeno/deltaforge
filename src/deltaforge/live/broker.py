"""Alpaca wrapper for the paper bot.

The backtest had to model both the option's price and its delta; live we get
both from the chain snapshot, which carries real bid/ask and greeks. That is
the single biggest difference between this module and its backtest
counterpart, and the reason the paper phase can settle the fill question the
backtest could only assume.

Every order is a limit order. Market orders on options with double-digit
percentage spreads are how a modelled edge disappears in practice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, OrderStatus, TimeInForce
from alpaca.trading.requests import LimitOrderRequest
from structlog import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Quote:
    occ: str
    bid: float
    ask: float
    delta: float | None
    iv: float | None
    strike: float
    expiry: date

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        return self.spread / self.mid if self.mid > 0 else 1.0


class Broker:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True) -> None:
        self.trading = TradingClient(api_key=api_key, secret_key=secret_key, paper=paper)
        self.options = OptionHistoricalDataClient(api_key=api_key, secret_key=secret_key)

    # -- account ------------------------------------------------------------

    def account(self):
        return self.trading.get_account()

    def equity(self) -> float:
        return float(self.account().equity)

    def is_open(self) -> bool:
        return bool(self.trading.get_clock().is_open)

    def option_positions(self) -> dict[str, object]:
        """Open option positions keyed by OCC symbol."""
        return {
            p.symbol: p
            for p in self.trading.get_all_positions()
            if getattr(p, "asset_class", None) and "option" in str(p.asset_class).lower()
        }

    # -- chain --------------------------------------------------------------

    def call_quotes(
        self, underlying: str, expiry_lo: date, expiry_hi: date,
        strike_lo: float, strike_hi: float,
    ) -> list[Quote]:
        """Live call quotes in the DTE/strike box, only those with a two-sided market."""
        chain = self.options.get_option_chain(
            OptionChainRequest(
                underlying_symbol=underlying,
                type="call",
                expiration_date_gte=expiry_lo,
                expiration_date_lte=expiry_hi,
                strike_price_gte=strike_lo,
                strike_price_lte=strike_hi,
            )
        )
        out = []
        for occ, snap in chain.items():
            q = snap.latest_quote
            if q is None or not q.bid_price or not q.ask_price or q.ask_price <= q.bid_price:
                continue
            g = snap.greeks
            from deltaforge.data.occ import parse_occ_symbol

            _, exp, _, strike = parse_occ_symbol(occ)
            out.append(
                Quote(
                    occ=occ,
                    bid=float(q.bid_price),
                    ask=float(q.ask_price),
                    delta=float(g.delta) if g and g.delta is not None else None,
                    iv=float(snap.implied_volatility) if snap.implied_volatility else None,
                    strike=strike,
                    expiry=exp,
                )
            )
        return sorted(out, key=lambda x: (x.expiry, x.strike))

    def quote(self, occ: str) -> Quote | None:
        """Refresh one contract's quote (for repricing and exit pricing)."""
        from deltaforge.data.occ import parse_occ_symbol

        underlying, exp, _, strike = parse_occ_symbol(occ)
        for q in self.call_quotes(underlying, exp, exp, strike, strike):
            if q.occ == occ:
                return q
        return None

    # -- orders -------------------------------------------------------------

    def buy_to_open(self, occ: str, qty: int, limit: float) -> str:
        order = self.trading.submit_order(
            LimitOrderRequest(
                symbol=occ,
                qty=qty,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=round(limit, 2),
            )
        )
        log.info("broker.buy", occ=occ, qty=qty, limit=round(limit, 2), order=str(order.id))
        return str(order.id)

    def sell_to_close(self, occ: str, qty: int, limit: float) -> str:
        order = self.trading.submit_order(
            LimitOrderRequest(
                symbol=occ,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
                limit_price=round(max(limit, 0.01), 2),
            )
        )
        log.info("broker.sell", occ=occ, qty=qty, limit=round(limit, 2), order=str(order.id))
        return str(order.id)

    def get_order(self, order_id: str):
        return self.trading.get_order_by_id(order_id)

    def cancel(self, order_id: str) -> None:
        try:
            self.trading.cancel_order_by_id(order_id)
        except Exception as exc:  # noqa: BLE001 — already-filled orders raise; not fatal
            log.warning("broker.cancel_failed", order=order_id, error=str(exc)[:150])

    @staticmethod
    def is_filled(order) -> bool:
        return order.status == OrderStatus.FILLED

    @staticmethod
    def fill_price(order) -> float | None:
        return float(order.filled_avg_price) if order.filled_avg_price else None

    @staticmethod
    def filled_at(order) -> str:
        ts: datetime | None = order.filled_at
        return ts.isoformat(timespec="seconds") if ts else ""
