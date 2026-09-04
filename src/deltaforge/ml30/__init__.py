"""The ML30 signal code the live bot runs on, vendored so the repo is self-contained.

Copied verbatim from the author's ml30-sp500-strategy repository at commit
``c7ad990`` (2026-09-02) — the same checkout the backtests and the paper bot
imported through ``deltaforge.ml30_bridge`` during the hackathon. Only the
import paths and ``settings.PROJECT_ROOT`` were changed so the modules
resolve inside this package and read ``.env`` from this repo's root.

What is here is exactly the surface the bot calls: the 21/55 cross entry
(``entry``), the indicators it needs (``indicators``), the frozen 8-bar
pivot stop (``sizing``), the ``Direction`` enum, the Alpaca historical
client and its settings. The backtest-only pieces (``Coordinator``,
``Trade``, ``ExitLogic``) are not vendored; ``ml30_bridge`` still resolves
them from an external checkout when one is present.
"""

VENDORED_FROM = "ml30-sp500-strategy"
VENDORED_COMMIT = "c7ad990"
