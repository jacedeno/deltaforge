"""DeltaForge runtime configuration.

Lives inside the package (not in the top-level ``config/`` directory) on
purpose: the ml30 bridge puts the ml30-sp500-strategy repo at ``sys.path[0]``,
whose top-level ``config`` package would collide with any importable
``config`` here. The repo-root ``config/`` directory therefore holds only
data files (JSON universes, TOML parameter sets), never Python.

Alpaca credentials are NOT duplicated here — they come from the ml30 repo's
``.env`` via ``config.settings`` once the bridge is up (see ``ml30_bridge``).
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

ML30_REPO_PATH: Path = Path(
    os.environ.get("ML30_REPO_PATH", "~/repos/ml30-sp500-strategy")
).expanduser()

CONFIG_DIR: Path = PROJECT_ROOT / "config"
CACHE_DIR: Path = PROJECT_ROOT / "data" / "cache"
SIP_30M_CACHE_DIR: Path = CACHE_DIR / "sip_30m"
OPTIONS_CACHE_DIR: Path = CACHE_DIR / "options"
REPORTS_DIR: Path = PROJECT_ROOT / "reports"

UNIVERSE_FILE: Path = CONFIG_DIR / "universe_sub150.json"

# Account constants from docs/ANALYSIS.md — the $3,000 real-money account.
ACCOUNT_EQUITY: float = 3000.0
MAX_CONCURRENT_POSITIONS: int = 3
MAX_DEBIT_DOLLARS: float = 150.0
MAX_DEBIT_EQUITY_PCT: float = 0.05

# Universe filter: sub-$150 half of the 80-name liquid universe.
UNIVERSE_PRICE_CAP: float = 150.0


def alpaca_keys() -> tuple[str, str]:
    """Alpaca (key, secret) — process env first, ml30's .env as fallback.

    Source the canonical file before running data scripts:
        set -a; source ~/.secrets/alpaca-thetaforge-competition.env; set +a
    (the keys in ml30's own .env were found revoked on 2026-08-28).
    """
    key, secret = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if key and secret:
        return key, secret
    from deltaforge import ml30_bridge  # noqa: F401  (puts ml30 on sys.path)
    from config.settings import settings as ml30_settings

    return (
        ml30_settings.alpaca.api_key.get_secret_value(),
        ml30_settings.alpaca.secret_key.get_secret_value(),
    )
