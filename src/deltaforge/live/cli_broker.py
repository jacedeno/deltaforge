"""Order routing through the Alpaca CLI.

The hackathon requires the agent to trade through Alpaca's MCP server or
CLI rather than the raw REST API. The bot is a deterministic Python process,
so the CLI is the natural fit: every order it places, polls or cancels is an
``alpaca order …`` invocation, and the SDK is kept only for what is not an
order — account, clock, positions and the option chain.

Credentials never touch disk. The CLI reads ``ALPACA_API_KEY`` /
``ALPACA_SECRET_KEY`` from its environment (it says so itself: "For
CI/automation, use ALPACA_API_KEY and ALPACA_SECRET_KEY env vars"), so they
are passed on each subprocess and nowhere else; no profile is written.

Two CLI habits shape the parsing. Output is JSON. Failures are also JSON —
an object carrying an ``error`` key — and the process may still exit 0, so
the error key, not the exit code, is what decides.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime

from structlog import get_logger

from deltaforge.live.broker import Broker

log = get_logger(__name__)


class CliError(RuntimeError):
    """The CLI reported an error object, or could not be run at all."""


@dataclass(frozen=True, slots=True)
class CliOrder:
    """The slice of an Alpaca order the executor reads back."""

    id: str
    status: str
    filled_avg_price: float | None
    filled_at: datetime | None

    @classmethod
    def from_json(cls, o: dict) -> "CliOrder":
        px = o.get("filled_avg_price")
        ts = o.get("filled_at")
        return cls(
            id=str(o["id"]),
            status=str(o.get("status", "")),
            filled_avg_price=float(px) if px not in (None, "") else None,
            filled_at=datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None,
        )


class CliBroker(Broker):
    """A ``Broker`` whose orders go through ``alpaca order …``; everything else is inherited."""

    def __init__(self, api_key: str, secret_key: str, paper: bool = True, binary: str = "alpaca") -> None:
        super().__init__(api_key, secret_key, paper=paper)
        self._env = {
            **{k: v for k, v in os.environ.items() if not k.startswith("ALPACA_")},
            "ALPACA_API_KEY": api_key,
            "ALPACA_SECRET_KEY": secret_key,
            "ALPACA_PAPER": "true" if paper else "false",
        }
        self.binary = shutil.which(binary) or binary

    # -- plumbing -----------------------------------------------------------

    def _run(self, *args: str) -> dict:
        argv = [self.binary, *args, "--quiet"]
        try:
            proc = subprocess.run(argv, env=self._env, capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CliError(f"alpaca CLI could not run: {exc}") from exc
        out = proc.stdout.strip()
        if not out:
            if proc.returncode != 0:
                raise CliError(f"alpaca {' '.join(args[:2])}: exit {proc.returncode}: {proc.stderr.strip()[:200]}")
            return {}
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            raise CliError(f"alpaca {' '.join(args[:2])}: non-JSON output: {out[:200]}") from exc
        if isinstance(data, dict) and data.get("error"):
            raise CliError(f"alpaca {' '.join(args[:2])}: {data['error']}")
        return data

    def _submit(self, occ: str, qty: int, side: str, intent: str, limit: float) -> str:
        data = self._run(
            "order", "submit",
            "--symbol", occ,
            "--qty", str(qty),
            "--side", side,
            "--type", "limit",
            "--limit-price", f"{limit:.2f}",
            "--time-in-force", "day",
            "--position-intent", intent,
        )
        return str(data["id"])

    # -- orders (the surface the executor calls) ----------------------------

    def buy_to_open(self, occ: str, qty: int, limit: float) -> str:
        limit = round(limit, 2)
        order_id = self._submit(occ, qty, "buy", "buy_to_open", limit)
        log.info("broker.buy", occ=occ, qty=qty, limit=limit, order=order_id, via="cli")
        return order_id

    def sell_to_close(self, occ: str, qty: int, limit: float) -> str:
        limit = round(max(limit, 0.01), 2)
        order_id = self._submit(occ, qty, "sell", "sell_to_close", limit)
        log.info("broker.sell", occ=occ, qty=qty, limit=limit, order=order_id, via="cli")
        return order_id

    def get_order(self, order_id: str) -> CliOrder:
        return CliOrder.from_json(self._run("order", "get", "--order-id", order_id))

    def cancel(self, order_id: str) -> None:
        try:
            self._run("order", "cancel", "--order-id", order_id)
        except CliError as exc:  # already-filled orders error; not fatal
            log.warning("broker.cancel_failed", order=order_id, error=str(exc)[:150], via="cli")

    @staticmethod
    def is_filled(order) -> bool:
        return str(order.status).lower() == "filled"

    @staticmethod
    def fill_price(order) -> float | None:
        return order.filled_avg_price

    @staticmethod
    def filled_at(order) -> str:
        return order.filled_at.isoformat(timespec="seconds") if order.filled_at else ""
