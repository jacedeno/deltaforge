"""Single import seam to the ML30 signal code.

The live bot's surface — the 21/55 cross entry, its indicators, the frozen
8-bar pivot stop, the ``Direction`` enum, the Alpaca historical client and
its settings — is vendored in ``deltaforge.ml30`` (see that package's
docstring for provenance), so the repository runs on its own. Every
DeltaForge import of ML30 code MUST still go through this module, never
``from deltaforge.ml30.entry import ...`` directly, so the dependency
surface stays auditable in one place.

The backtest-only symbols (``Coordinator``, ``Trade``, ``ExitLogic``, …) are
not vendored. They resolve lazily from an external ml30-sp500-strategy
checkout at ``ML30_REPO_PATH`` when one is present; the bot has no business
failing to start over a symbol it never calls.

For reproducibility, run artifacts should record ``ml30_commit()`` alongside
DeltaForge's own commit.
"""

from __future__ import annotations

import subprocess
import sys

from deltaforge.ml30 import VENDORED_COMMIT, VENDORED_FROM
from deltaforge.ml30.alpaca_client import AlpacaClientError, AlpacaHistoricalClient
from deltaforge.ml30.entry import EntryLogic
from deltaforge.ml30.indicators import add_indicators
from deltaforge.ml30.settings import Settings as Ml30Settings
from deltaforge.ml30.sizing import calculate_initial_stop
from deltaforge.settings import ML30_REPO_PATH


def external_repo_available() -> bool:
    """True when a full ml30-sp500-strategy checkout is reachable for the backtest-only symbols."""
    return (ML30_REPO_PATH / "strategy" / "entry.py").exists()


def _ensure_repo_on_path() -> None:
    if not external_repo_available():
        raise RuntimeError(
            f"ml30-sp500-strategy repo not found at {ML30_REPO_PATH} "
            "(set ML30_REPO_PATH to override). The live bot does not need it; "
            "the backtest-only symbols do."
        )
    path = str(ML30_REPO_PATH)
    if path not in sys.path:
        sys.path.insert(0, path)


def ml30_commit() -> str:
    """Provenance of the signal code: the external checkout's HEAD when present, else the vendored pin."""
    if external_repo_available():
        return subprocess.run(
            ["git", "-C", str(ML30_REPO_PATH), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    return f"{VENDORED_FROM}@{VENDORED_COMMIT} (vendored)"


def deltaforge_commit() -> str:
    """Current commit SHA of this repo, for run provenance."""
    from deltaforge.settings import PROJECT_ROOT

    return subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def settings_with_credentials(api_key: str, secret_key: str) -> "Ml30Settings":
    """An ML30 Settings carrying credentials we chose, not ones it found.

    ``AlpacaHistoricalClient`` otherwise resolves keys from a ``.env`` on
    disk. Inheriting whatever happens to be there is how a bot ends up
    trading an account nobody pointed it at, so the caller passes them in.
    """
    from pydantic import SecretStr

    s = Ml30Settings()
    s.alpaca.api_key = SecretStr(api_key)
    s.alpaca.secret_key = SecretStr(secret_key)
    return s


# Backtest-only: resolved on first use from the external checkout (PEP 562).
_LAZY = {
    "Coordinator": ("backtest.coordinator", "Coordinator"),
    "CoordinatorResult": ("backtest.coordinator", "CoordinatorResult"),
    "ENTRY_RANKINGS": ("backtest.coordinator", "ENTRY_RANKINGS"),
    "Trade": ("backtest.trade", "Trade"),
    "ExitLogic": ("strategy.exit", "ExitLogic"),
    "ExitReason": ("strategy.exit", "ExitReason"),
}


def __getattr__(name: str):
    if name in _LAZY:
        module, attr = _LAZY[name]
        import importlib

        _ensure_repo_on_path()
        return getattr(importlib.import_module(module), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


from deltaforge.ml30.direction import Direction  # noqa: E402  (vendored; was lazy)

__all__ = [
    "ENTRY_RANKINGS",
    "AlpacaClientError",
    "AlpacaHistoricalClient",
    "Coordinator",
    "CoordinatorResult",
    "Direction",
    "EntryLogic",
    "ExitLogic",
    "ExitReason",
    "Ml30Settings",
    "Trade",
    "add_indicators",
    "calculate_initial_stop",
    "deltaforge_commit",
    "external_repo_available",
    "ml30_commit",
    "settings_with_credentials",
]
