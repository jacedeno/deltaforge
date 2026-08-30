"""DeltaForge paper bot — run on AlgoTrader (.102), beside its dashboard.

Wakes shortly after each 30-minute bar closes during regular hours, runs one
pass (manage open positions, then look for entries), and sleeps. Everything
it does is journalled to SQLite and to an event log the dashboard narrates.

    python scripts/run_paper_bot.py --env-file ~/.secrets/alpaca-deltaforge.env

The env file must define ALPACA_PAPER_API_KEY and ALPACA_PAPER_SECRET. It is
passed explicitly and never inferred: pointing this at the wrong account is
the one mistake with no undo.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from deltaforge.live.broker import Broker
from deltaforge.live.events import ERROR, EventLog
from deltaforge.live.executor import BotConfig, Executor
from deltaforge.live.journal import Journal
from deltaforge.settings import PROJECT_ROOT, UNIVERSE_FILE

log = structlog.get_logger(__name__)

BAR_MINUTES = 30
SETTLE_SECONDS = 20  # let the bar close and the data land before scanning
_stop = False


def _handle_signal(signum, _frame):
    global _stop
    _stop = True
    log.info("bot.signal", signum=signum)


def load_env(path: Path) -> tuple[str, str]:
    """Read the env file directly — an explicit file always outranks os.environ.

    ml30 learned this the hard way: a stray ALPACA_PAPER_API_KEY in the
    environment silently outranked --env-file and two bots reported the same
    account. Here the file wins, or we refuse to start.
    """
    if not path.exists():
        raise SystemExit(f"env file not found: {path}")
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")
    key = values.get("ALPACA_PAPER_API_KEY")
    secret = values.get("ALPACA_PAPER_SECRET")
    if not key or not secret:
        raise SystemExit(f"{path} must define ALPACA_PAPER_API_KEY and ALPACA_PAPER_SECRET")
    return key, secret


def seconds_to_next_bar() -> float:
    now = datetime.now(UTC)
    minute = (now.minute // BAR_MINUTES + 1) * BAR_MINUTES
    nxt = now.replace(second=0, microsecond=0, minute=0) + timedelta(minutes=minute)
    return max(5.0, (nxt - now).total_seconds() + SETTLE_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--universe-file", type=Path, default=UNIVERSE_FILE)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--logs-dir", type=Path, default=PROJECT_ROOT / "logs")
    parser.add_argument("--position-size", type=float, default=300.0)
    parser.add_argument("--max-slots", type=int, default=15)
    parser.add_argument("--delta", type=float, default=0.55)
    parser.add_argument("--dte-min", type=int, default=7)
    parser.add_argument("--dte-max", type=int, default=14)
    parser.add_argument("--haircut-cap", type=float, default=0.5)
    parser.add_argument("--once", action="store_true", help="single pass, then exit")
    parser.add_argument("--dry-run", action="store_true", help="scan and log, place no orders")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    key, secret = load_env(args.env_file)
    broker = Broker(key, secret, paper=True)
    account = broker.account()
    universe = json.loads(args.universe_file.read_text())["symbols"]

    journal = Journal(args.data_dir / "deltaforge.db")
    eventlog = EventLog(args.logs_dir / "events.jsonl", args.data_dir / "heartbeat.json")

    cfg = BotConfig(
        position_size=args.position_size,
        max_slots=args.max_slots,
        target_delta=args.delta,
        dte_min=args.dte_min,
        dte_max=args.dte_max,
        haircut_cap=args.haircut_cap,
    )
    executor = Executor(broker, journal, eventlog, universe, cfg, credentials=(key, secret))

    log.info(
        "bot.start",
        account=account.account_number,
        equity=float(account.equity),
        universe=len(universe),
        position_size=cfg.position_size,
        slots=executor.slots(float(account.equity)),
        dry_run=args.dry_run,
    )
    if args.dry_run:
        log.warning("bot.dry_run", note="no orders will be placed")
        os.environ["DELTAFORGE_DRY_RUN"] = "1"

    try:
        while not _stop:
            try:
                executor.run_once()
            except Exception as exc:  # noqa: BLE001 — one bad pass must not kill the bot
                log.exception("bot.pass_failed")
                eventlog.emit(ERROR, detail=str(exc)[:300])
                eventlog.beat(ok=False, note=str(exc)[:120])
            if args.once:
                break
            wait = seconds_to_next_bar()
            log.info("bot.sleep", seconds=round(wait))
            deadline = time.monotonic() + wait
            while not _stop and time.monotonic() < deadline:
                time.sleep(min(5.0, deadline - time.monotonic()))
    finally:
        journal.close()
        log.info("bot.stopped")


if __name__ == "__main__":
    sys.exit(main())
