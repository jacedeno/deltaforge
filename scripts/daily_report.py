#!/usr/bin/env python3
"""Twice-daily DeltaForge report, sent to Telegram.

Run by deltaforge-report@open.timer (09:07 CT, half an hour into the session,
after the first 30-minute pass) and deltaforge-report@close.timer (15:12 CT,
after the close). It reads the same three sources the dashboard does — the
Alpaca account, the bot's journal and its event log — plus the systemd state,
because a service showing `active` has been wrong about this bot before.

Standard library only, so it runs under the system python3 and does not
depend on the bot's virtualenv being healthy. Every section degrades to an
error line rather than suppressing the message: a report that fails silently
is the failure mode this exists to catch.

    python3 scripts/daily_report.py --kind open --print     # no Telegram
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
TRADING = "https://paper-api.alpaca.markets/v2"
DATA = "https://data.alpaca.markets"
BOT_UNIT = "deltaforge-paper-bot"
RETIRED_UNITS = ("deltaforge-100k-bot", "deltaforge-bot", "ml30-live-bot-v1-5m-top20")
# The bot writes a heartbeat every pass; anything older than this during the
# session means the loop is stuck even if systemd says it is running.
STALE_HEARTBEAT_S = 45 * 60
DTE_EXIT = 5


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class Alpaca:
    def __init__(self, key: str, secret: str) -> None:
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    def get(self, url: str):
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)

    def trading(self, path: str):
        return self.get(f"{TRADING}{path}")

    def data(self, path: str):
        return self.get(f"{DATA}{path}")


def money(v: float) -> str:
    return f"{'-' if v < 0 else ''}${abs(v):,.2f}"


def signed(v: float) -> str:
    return f"{'+' if v >= 0 else '-'}${abs(v):,.2f}"


def systemctl(*args: str) -> str:
    r = subprocess.run(["systemctl", *args], capture_output=True, text=True)
    return r.stdout.strip() or r.stderr.strip()


def section_health(data_dir: Path, events_today: list[dict], market_open: bool) -> list[str]:
    lines = []
    active = systemctl("is-active", BOT_UNIT)
    enabled = systemctl("is-enabled", BOT_UNIT)
    flag = "OK" if active == "active" and enabled == "enabled" else "ALERT"
    lines.append(f"{flag} bot {active}/{enabled}")
    try:
        hb = json.loads((data_dir / "heartbeat.json").read_text())
        age = (datetime.now(UTC) - datetime.fromisoformat(hb["ts"])).total_seconds()
        fails = int(hb.get("consecutive_failures", 0))
        stale = market_open and age > STALE_HEARTBEAT_S
        tag = "ALERT" if stale or fails >= 2 else "OK"
        lines.append(f"{tag} heartbeat {age / 60:.0f} min ago, {fails} failed passes")
    except Exception as e:  # noqa: BLE001 — the report must still go out
        lines.append(f"ALERT heartbeat unreadable: {e}")
    errors = [e for e in events_today if e.get("kind") == "error"]
    if errors:
        last = str(errors[-1].get("data", {}).get("detail", ""))[:140]
        lines.append(f"ALERT {len(errors)} errors today, last: {last}")
    retired = [u for u in RETIRED_UNITS if systemctl("is-active", u) == "active"]
    if retired:
        lines.append(f"ALERT retired unit running: {', '.join(retired)}")
    return lines


def section_account(api: Alpaca, inception_equity: float) -> tuple[list[str], float]:
    a = api.trading("/account")
    equity, last = float(a["equity"]), float(a["last_equity"])
    cash = float(a["cash"])
    since = equity - inception_equity
    lines = [
        f"Equity {money(equity)}  day {signed(equity - last)}",
        f"Since inception {signed(since)} ({since / inception_equity * 100:+.2f}%)",
        f"Cash {money(cash)}",
    ]
    return lines, equity


def open_rows(db: Path) -> list[sqlite3.Row]:
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return con.execute("SELECT * FROM trades WHERE status IN ('open','pending') ORDER BY entry_ts").fetchall()
    finally:
        con.close()


def closed_today(db: Path, day: date) -> list[sqlite3.Row]:
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM trades WHERE status = 'closed' AND exit_ts IS NOT NULL").fetchall()
    finally:
        con.close()
    return [r for r in rows if datetime.fromisoformat(r["exit_ts"]).astimezone(ET).date() == day]


def section_positions(api: Alpaca, rows: list[sqlite3.Row], equity: float, max_slots: int) -> list[str]:
    if not rows:
        return [f"No open positions (0 of {max_slots} slots)"]
    occs = [r["occ"] for r in rows]
    syms = sorted({r["symbol"] for r in rows})
    quotes = api.data(f"/v1beta1/options/quotes/latest?symbols={','.join(occs)}").get("quotes", {})
    trades = api.data(f"/v2/stocks/trades/latest?symbols={','.join(syms)}&feed=iex").get("trades", {})
    deployed = sum(r["debit"] or 0 for r in rows)
    lines = [f"{len(rows)} open of {max_slots} slots, {money(deployed)} deployed ({deployed / equity * 100:.0f}% of equity)"]
    today = datetime.now(ET).date()
    for r in rows:
        if r["status"] == "pending":
            lines.append(f"ALERT {r['symbol']} {r['occ']} still pending")
            continue
        q = quotes.get(r["occ"], {})
        mid = (q["bp"] + q["ap"]) / 2 if q.get("bp") is not None and q.get("ap") is not None else None
        pl = (mid - r["entry_fill"]) * 100 * r["contracts"] if mid is not None else None
        spot = trades.get(r["symbol"], {}).get("p")
        dte = (date.fromisoformat(r["expiry"]) - today).days
        head = f"{r['symbol']} {r['strike']:g}c x{r['contracts']} in {r['entry_fill']:.2f}"
        if mid is not None:
            head += f" mid {mid:.2f} {signed(pl)} ({pl / r['debit'] * 100:+.0f}%)"
        lines.append(head)
        if spot:
            to_stop = (spot - r["stop_price"]) / spot * 100
            to_tgt = (r["target_price"] - spot) / spot * 100
            exit_in = dte - DTE_EXIT
            lines.append(
                f"   spot {spot:.2f} | stop {r['stop_price']:.2f} ({to_stop:.1f}% away)"
                f" | target {r['target_price']:.2f} ({to_tgt:.1f}%) | {dte} DTE, clock exit in {exit_in}d"
            )
    return lines


def section_reconcile(api: Alpaca, rows: list[sqlite3.Row]) -> list[str]:
    broker = {p["symbol"]: p for p in api.trading("/positions") if p.get("asset_class") == "us_option"}
    journal = {r["occ"] for r in rows if r["status"] == "open"}
    lines = []
    for occ in sorted(journal - broker.keys()):
        lines.append(f"ALERT journal open, broker flat: {occ}")
    for occ in sorted(broker.keys() - journal):
        lines.append(f"ALERT broker holds, journal does not: {occ}")
    open_orders = api.trading("/orders?status=open")
    if open_orders:
        lines.append(f"ALERT {len(open_orders)} open orders at the broker")
    return lines or ["OK journal and broker agree, no open orders"]


def section_activity(events: list[dict], closed: list[sqlite3.Row]) -> list[str]:
    kinds = Counter(e.get("kind") for e in events)
    skips = Counter(e.get("data", {}).get("reason") for e in events if e.get("kind") == "skip")
    fills = [e["data"] for e in events if e.get("kind") == "order_filled" and "asked" in e.get("data", {})]
    lines = [f"{kinds['scan']} scans, {kinds['signal']} signals, {len(fills)} entries"]
    for f in fills:
        lines.append(f"   in {f['occ']} x{f['qty']} asked {f['asked']:.2f} got {f['got']:.2f}")
    for r in closed:
        lines.append(f"   out {r['occ']} {r['exit_reason']} {signed(r['pnl'] or 0)}")
    if skips:
        lines.append("Skipped: " + ", ".join(f"{k} {v}" for k, v in skips.most_common()))
    return lines


def events_on(path: Path, day: date) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if datetime.fromisoformat(e["ts"]).astimezone(ET).date() == day:
            out.append(e)
    return out


def guarded(title: str, fn, *args) -> list[str]:
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001
        return [f"ALERT {title} failed: {str(e)[:160]}"]


def build(args: argparse.Namespace) -> str | None:
    env = load_env(args.env_file)
    api = Alpaca(env["ALPACA_PAPER_API_KEY"], env["ALPACA_PAPER_SECRET"])
    today = datetime.now(ET).date()

    # Nothing to report on a day the market never opened.
    cal = api.trading(f"/calendar?start={today}&end={today}")
    if not cal or cal[0].get("date") != today.isoformat():
        return None
    market_open = bool(api.trading("/clock").get("is_open"))

    events = events_on(args.logs_dir / "events.jsonl", today)
    db = args.data_dir / "deltaforge.db"
    rows = open_rows(db)

    title = "DeltaForge open check" if args.kind == "open" else "DeltaForge close report"
    try:
        acct_lines, equity = section_account(api, args.inception_equity)
    except Exception as e:  # noqa: BLE001
        acct_lines, equity = [f"ALERT account failed: {str(e)[:160]}"], 0.0
    blocks = [
        ("Health", section_health(args.data_dir, events, market_open)),
        ("Account", acct_lines),
        ("Positions", guarded("positions", section_positions, api, rows, equity or 1.0, args.max_slots)),
        ("Reconcile", guarded("reconcile", section_reconcile, api, rows)),
        ("Today", guarded("activity", section_activity, events, closed_today(db, today))),
    ]
    alert = any(l.startswith("ALERT") for _, ls in blocks for l in ls)
    head = f"<b>{'⚠️ ' if alert else ''}{title}</b> · {today:%a %b %d} · PA3PYB0A7982"
    body = "\n\n".join(f"<b>{t}</b>\n<pre>{html.escape(chr(10).join(ls))}</pre>" for t, ls in blocks)
    return f"{head}\n\n{body}"


def send(token: str, chat_id: str, text: str) -> None:
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"}
    ).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20) as r:
        if not json.load(r).get("ok"):
            raise RuntimeError("telegram refused the message")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--kind", choices=["open", "close"], required=True)
    p.add_argument("--env-file", type=Path, default=Path("/root/.secrets/alpaca-deltaforge-paper.env"))
    p.add_argument("--telegram-env", type=Path, default=Path("/root/.secrets/telegram-deltaforge.env"))
    p.add_argument("--data-dir", type=Path, default=Path("/root/repos/deltaforge/data-paper"))
    p.add_argument("--logs-dir", type=Path, default=Path("/root/repos/deltaforge/logs-paper"))
    p.add_argument("--inception-equity", type=float, default=5000.0)
    p.add_argument("--max-slots", type=int, default=15)
    p.add_argument("--print", action="store_true", help="print instead of sending")
    args = p.parse_args()

    try:
        text = build(args)
    except Exception as e:  # noqa: BLE001 — still tell Jose the report itself broke
        text = f"<b>⚠️ DeltaForge {args.kind} report failed</b>\n<pre>{html.escape(str(e)[:400])}</pre>"
    if text is None:
        print("market closed today, nothing to report")
        return 0
    if args.print:
        print(text)
        return 0
    tg = load_env(args.telegram_env)
    send(tg["TELEGRAM_BOT_TOKEN"], tg["TELEGRAM_CHAT_ID"], text)
    print("sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
