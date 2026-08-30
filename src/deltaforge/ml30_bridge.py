"""Single import seam to the validated ml30-sp500-strategy code.

ml30-sp500-strategy is not an installable package (top-level packages with
absolute cross-imports, no ``[project]`` table), and it must not be modified —
it runs the live paper bots. So DeltaForge reaches it the one honest way
left: this module inserts the repo at ``sys.path[0]`` and re-exports exactly
the symbols DeltaForge is allowed to use. Every DeltaForge import of ml30
code MUST go through this module — never ``from strategy.entry import ...``
directly — so the dependency surface stays auditable in one place.

Position 0 on ``sys.path`` also guarantees ml30's regular packages
(``strategy``, ``backtest``, ``data``, ``config``) win over any same-named
namespace directories in the DeltaForge repo root.

For reproducibility, run artifacts should record ``ml30_commit()`` alongside
DeltaForge's own commit.
"""

from __future__ import annotations

import subprocess
import sys

from deltaforge.settings import ML30_REPO_PATH


def _ensure_repo_on_path() -> None:
    marker = ML30_REPO_PATH / "strategy" / "entry.py"
    if not marker.exists():
        raise RuntimeError(
            f"ml30-sp500-strategy repo not found at {ML30_REPO_PATH} "
            "(set ML30_REPO_PATH to override)"
        )
    path = str(ML30_REPO_PATH)
    if path not in sys.path:
        sys.path.insert(0, path)


def ml30_commit() -> str:
    """Current commit SHA of the ml30 repo, for run provenance."""
    return subprocess.run(
        ["git", "-C", str(ML30_REPO_PATH), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def deltaforge_commit() -> str:
    """Current commit SHA of this repo, for run provenance."""
    from deltaforge.settings import PROJECT_ROOT

    return subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


_ensure_repo_on_path()

# Re-exports — the whole ml30 surface DeltaForge is allowed to touch.
from backtest.coordinator import (  # noqa: E402
    ENTRY_RANKINGS,
    Coordinator,
    CoordinatorResult,
)
from backtest.trade import Trade  # noqa: E402
from config.settings import Settings as Ml30Settings  # noqa: E402
from data.alpaca_client import (  # noqa: E402
    AlpacaClientError,
    AlpacaHistoricalClient,
)


def settings_with_credentials(api_key: str, secret_key: str) -> "Ml30Settings":
    """An ml30 Settings carrying credentials we chose, not ones it found.

    ``AlpacaHistoricalClient`` otherwise resolves keys from the ml30 repo's
    own ``.env``, which is dead on both machines as of 2026-08-30 (HTTP 401).
    Inheriting whatever happens to be on disk is also how a bot ends up
    trading an account nobody pointed it at, so the caller passes them in.
    """
    from pydantic import SecretStr

    s = Ml30Settings()
    s.alpaca.api_key = SecretStr(api_key)
    s.alpaca.secret_key = SecretStr(secret_key)
    return s
from strategy.direction import Direction  # noqa: E402
from strategy.entry import EntryLogic  # noqa: E402
from strategy.exit import ExitLogic, ExitReason  # noqa: E402
from strategy.indicators import add_indicators  # noqa: E402
from strategy.sizing import calculate_initial_stop  # noqa: E402

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
    "ml30_commit",
    "settings_with_credentials",
]
