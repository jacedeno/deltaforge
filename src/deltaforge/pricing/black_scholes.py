"""Black-Scholes pricing, greeks, and implied volatility.

Pure math, no I/O. Used two ways:
- as the synthetic pricer for the pre-2024 extension (with the RV-calibrated
  IV model from ``pricing.iv``), and
- as the last rung of the mark fallback ladder inside the real-data window,
  when an illiquid strike printed no bar near the timestamp.

Conventions: ``T`` in years (ACT/365), ``sigma`` annualized, European
exercise, no dividends. American early-exercise premium on 14-21 DTE
out-of-the-money-ish calls is negligible next to the modeled bid-ask
haircut, so it is deliberately ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.optimize import brentq
from scipy.stats import norm

_MIN_T = 1e-6
_MIN_SIGMA = 1e-4


def _d1_d2(s: float, k: float, t: float, r: float, sigma: float) -> tuple[float, float]:
    d1 = (math.log(s / k) + (r + sigma**2 / 2) * t) / (sigma * math.sqrt(t))
    return d1, d1 - sigma * math.sqrt(t)


def intrinsic(s: float, k: float, call_put: str) -> float:
    return max(s - k, 0.0) if call_put.upper() == "C" else max(k - s, 0.0)


def bs_price(s: float, k: float, t: float, r: float, sigma: float, call_put: str = "C") -> float:
    if t <= _MIN_T or sigma <= _MIN_SIGMA:
        return intrinsic(s, k, call_put)
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    if call_put.upper() == "C":
        return s * norm.cdf(d1) - k * math.exp(-r * t) * norm.cdf(d2)
    return k * math.exp(-r * t) * norm.cdf(-d2) - s * norm.cdf(-d1)


@dataclass(frozen=True, slots=True)
class Greeks:
    delta: float
    gamma: float
    theta: float  # per calendar day
    vega: float  # per 1.0 (100 vol points)


def bs_greeks(s: float, k: float, t: float, r: float, sigma: float, call_put: str = "C") -> Greeks:
    if t <= _MIN_T or sigma <= _MIN_SIGMA:
        itm = intrinsic(s, k, call_put) > 0
        sign = 1.0 if call_put.upper() == "C" else -1.0
        return Greeks(delta=sign if itm else 0.0, gamma=0.0, theta=0.0, vega=0.0)
    d1, d2 = _d1_d2(s, k, t, r, sigma)
    pdf = norm.pdf(d1)
    if call_put.upper() == "C":
        delta = norm.cdf(d1)
        theta_y = -s * pdf * sigma / (2 * math.sqrt(t)) - r * k * math.exp(-r * t) * norm.cdf(d2)
    else:
        delta = norm.cdf(d1) - 1.0
        theta_y = -s * pdf * sigma / (2 * math.sqrt(t)) + r * k * math.exp(-r * t) * norm.cdf(-d2)
    return Greeks(
        delta=delta,
        gamma=pdf / (s * sigma * math.sqrt(t)),
        theta=theta_y / 365.0,
        vega=s * pdf * math.sqrt(t),
    )


def implied_vol(
    price: float,
    s: float,
    k: float,
    t: float,
    r: float,
    call_put: str = "C",
    lo: float = 0.01,
    hi: float = 5.0,
) -> float | None:
    """Back out sigma from an observed price; None when no root exists.

    No root means the observation is outside the arbitrage-free band for
    [lo, hi] — e.g. a stale bar below intrinsic. Callers must treat None as
    "unusable observation", not as zero vol.
    """
    if t <= _MIN_T:
        return None
    if price <= intrinsic(s, k, call_put) + 1e-9:
        return None

    def objective(sigma: float) -> float:
        return bs_price(s, k, t, r, sigma, call_put) - price

    try:
        if objective(lo) * objective(hi) > 0:
            return None
        return float(brentq(objective, lo, hi, xtol=1e-6))
    except ValueError:
        return None
