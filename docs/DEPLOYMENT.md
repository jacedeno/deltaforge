# Running DeltaForge

Both halves live on **AlgoTrader (192.168.68.102)**, in `/root/repos/deltaforge`:
the bot writes `data/deltaforge.db` and `logs/events.jsonl`, and the dashboard
reads them from `dashboard/` via `..`. That adjacency is the whole reason they
share a host — the dashboard has no network path to the journal otherwise.

GeekForge (.80) is where this is developed and where the backtests run. It does
not run the bot.

## Account

Alpaca paper **PA3YN2XF0XWT**, options trading level 3, opened 2026-08-31 with
$100,000. Keys: `homelab-secrets/alpaca-deltaforge-100k.env`, mirrored to
`/root/.secrets/alpaca-deltaforge-100k.env` on AlgoTrader and to
`dashboard/.env.local` (Next reads that at boot — a running dashboard keeps
using an old key until restarted).

Inception is **2026-08-31** at **$100,000.00**.

**One bot, one account.** The fleet runs exactly three bots — ml30's real-money
V1-5m-Top20 and DeltaForge here, both on AlgoTrader, plus a third on
GeekForge. DeltaForge is this account and nothing else.

### Two retired accounts

**PA3HBSB6VT9C** held the $300-a-position instance from 2026-08-30 to
2026-08-31. Its credentials stopped authenticating while the service was still
up, so its last hours were spent raising `401 Authorization Required` on the
opening `get_clock` of every pass — 29 of them — without ever reaching the
order path. Stopped and disabled 2026-08-31. The unit file is kept at
`deploy/deltaforge-bot.service`; reviving it means minting new keys first, and
deciding whether two DeltaForge accounts are worth the ambiguity a second time.

**PA35JTJLBB0O** was borrowed for a few hours on 2026-08-30 from the retired
`ml30-paper-bot-v1-5m-frac` service. Abandoned the same day: the inherited
positions and months of unrelated portfolio history made every number
ambiguous. Its liquidation orders remain queued so that account closes itself
out.

## Bot

```bash
ssh root@192.168.68.102
cd /root/repos/deltaforge
export PATH=$PATH:/root/.local/bin

# one pass, no orders — the safe way to check a change
uv run python scripts/run_paper_bot.py \
    --env-file /root/.secrets/alpaca-deltaforge-100k.env \
    --position-size 7000 --max-slots 14 \
    --data-dir /root/repos/deltaforge/data-100k \
    --logs-dir /root/repos/deltaforge/logs-100k \
    --once --dry-run

# the real thing
uv run python scripts/run_paper_bot.py \
    --env-file /root/.secrets/alpaca-deltaforge-100k.env \
    --position-size 7000 --max-slots 14 \
    --data-dir /root/repos/deltaforge/data-100k \
    --logs-dir /root/repos/deltaforge/logs-100k
```

`--env-file` is required and never inferred. ml30's own settings module carries
a long comment about why: a stray `ALPACA_PAPER_API_KEY` in the environment
once outranked `--env-file` and two bots reported the same account.

The script's own defaults are the backtest's: $300 a position, one slot per
$300 of equity capped at 15, 0.55 delta, 7–14 DTE, exit at 5 DTE, and **signals
whose 3R target sits under 5% away are refused**. Delta, DTE and the 5% target
gate are used as they stand; **sizing is overridden on the command line** —
`--position-size 7000 --max-slots 14` — and the journal is redirected to
`data-100k/` and `logs-100k/`.

Those directory flags are historical. They were named when a $3,000 sibling
owned the unsuffixed `data/` and `logs/`, and they stayed after it was retired
rather than risk a rename against a live journal.

### Why $7,000 a position

**Why $7,000 and not $10,000.** The budget sweep (`reports/budget/`) is an
inverted U on a $3,000 account: $150 a position returns +304%, $300 returns
+395%, and $500 returns +268% with the drawdown widening from -23% to -40%.
The optimum is $300, i.e. **10% of equity**. Scaling that to $100,000 would
say $10,000 — but the $300 cap was doing two jobs at once, sizing the position
*and* refusing 760 contracts as too expensive. That is why the winning run
held only 6.6 positions on average, about 66% invested.

At $100,000 the second job disappears: the contracts that were unaffordable at
$300 cost $400–1,200, and nothing is out of reach. More signals clear, so more
positions are held concurrently, and 10% each would sit near fully invested in
long premium — well past what the sweep actually tested. **$7,000 (7%) keeps
the validated ~66-70% exposure at the higher trade count.** Fourteen slots
rather than ten also spread the same money across more names, which matters
for a structure that wins 36.7% of the time and lives on its right tail.

Measured from the 1,623 backtested trades: 2.6 signals a session, median hold
3.8 days, mean concurrency 6.6 and a maximum of 28. Starting flat, the book
fills at roughly four positions a day and does not reach steady state for over
a week.

**This sizing is an extrapolation, not a measured point.** No sweep run
combined a large absolute budget with a 7% concentration, because a $3,000
account cannot express that combination. The strategy's worst historical
drawdown is -29%.

It was briefly meant to be checked against the $3,000 account running the same
code as a control. That never produced a single comparable session — the
control's credentials had already failed — and the account is now retired, so
**the 7% figure rests on the sweep and the reasoning above, not on a live A/B.**

### Two universes

| File | Used by | Screen |
|---|---|---|
| `config/universe_sub150.json` (45) | backtests | sub-$150 **at the 2020 start date** |
| `config/universe_liquid160.json` (160) | **the live bot** | 160 most liquid S&P 500 names, sector-capped, **no price cap** |

They are separate on purpose. Every artefact under `reports/` was produced on
the sub-$150 list, so repointing it would invalidate `docs/BACKTEST.md`
without changing a line of it.

The sub-$150 cut was right for a 2020-start backtest — filtering on today's
price would have been look-ahead — but six years on it describes nothing
useful: 16 of its 45 survivors now trade above $150 (LLY at $1,148, MU at
$822), and a signal on one can only ever end in `over_budget`. Live there is
no look-ahead to avoid, because the budget check prices the real contract at
the real moment. Measured on live chains, the swap takes the names actually
affordable at $300 from ~22 to **37**.

Rebuild with `scripts/build_liquid_universe.py --top-n 160` (needs SIP bars,
so source the SIP-entitled key file from `homelab-secrets` first, not the
bot's own key). It mirrors ml30's `build_broad_liquid_universe.py` — mean
per-bar dollar
volume, greedy per-sector cap, no feature selection — so the two stay
comparable.

**This is the one place live and backtest diverge.** The new names were never
backtested. That is defensible only because the universe was never fitted:
ml30's walk-forward study found no stock feature predicts forward P&L, which
is why the screen is liquidity alone. It is still worth watching per-symbol
results before trusting the widened list.

### Two environment facts that shaped the code

- **The account cannot query recent SIP data** ("subscription does not permit").
  Live bars come from **IEX**, matching the real-money ml30 bot on the same
  host. IEX is a thinner tape; measured against SIP over 20 days its 30-minute
  ranges run 3–8% narrower, which is small but not zero.
- **AlgoTrader's ml30 checkout is pinned at `ccade12` (2026-07-27)** — it is
  what the real-money bot runs and must not be pulled forward. The bridge
  imports only the four symbols the bot calls, all of which are
  signature-compatible there; everything else loads lazily.

## Dashboard

```bash
ssh root@192.168.68.102 'cd /root/repos/deltaforge && ./scripts/deploy_dashboard.sh'
```

Port **3779** (3777 and 3778 belong to neighbouring apps on this fleet,
3778 being the ml30 screener). The deploy script's kill is **port-scoped
on purpose**; `pkill next-server` would take the neighbours down.

`dashboard/.env.local` is not in git and is the whole configuration:

```
ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET   from alpaca-deltaforge-100k.env
DF_DB_PATH          .../data-100k/deltaforge.db
DF_EVENTS_PATH      .../logs-100k/events.jsonl
DF_HEARTBEAT_PATH   .../data-100k/heartbeat.json
DF_INCEPTION_DATE   2026-08-31
DF_INCEPTION_EQUITY 100000
```

**The three paths are not optional.** Without them the code falls back to
`../data` and `../logs`, which is the retired $300 bot's journal — a frozen one
that still parses, so the dashboard renders a plausible page of stale numbers
rather than failing. They are read at runtime by the route handlers, so a
restart is enough; no rebuild is needed to change an account.

After any account change, check `/api/snapshot` reports the account number you
expect, not just that the page loads.

Published at **https://deltaforge.geekendzone.net** through Cloudflare tunnel
CT 101 (`73869032-…`), ingress v183 → `http://192.168.68.102:3779`, with a
proxied CNAME on the zone.

**Entries paused for judging (2026-09-02)** — a systemd drop-in on
AlgoTrader (`deltaforge-100k-bot.service.d/override.conf`) runs the bot with
`--max-slots 1`: with six positions open no free slot ever exists, so exits
keep being managed while nothing new opens into the judged session. Revert
Friday by removing the drop-in, `daemon-reload`, restart.

### Order routing through the Alpaca CLI (added 2026-09-03, after the judged week)

The hackathon requires the agent to trade through Alpaca's MCP server or
CLI, not the raw REST API. During the judged week the bot placed its orders
through the official Python SDK (`alpaca-py`), and the supervisory agent
used the Alpaca MCP server only for read-only account checks. That gap was
closed the evening of Sep 3: `deltaforge.live.cli_broker.CliBroker` routes
every order the executor places — entries, stop/target/DTE exits, cancels
and fill polls — through `alpaca order submit / get / cancel`. The SDK is
kept for what is not an order: account, clock, positions and the option
chain. `scripts/run_paper_bot.py --broker cli` is the default; `--broker
sdk` (or `DF_BROKER=sdk`) restores the judged-week path.

Credentials are passed to each CLI subprocess as `ALPACA_API_KEY` /
`ALPACA_SECRET_KEY` and are written nowhere. CLI failures come back as JSON
objects carrying an `error` key, sometimes with exit code 0, so the broker
decides on that key rather than the exit status.

Verified live on 2026-09-03 21:47 CDT against a spare paper account (not the
judged one, which stays untouched): `buy_to_open` of one
`SPY260908C00500000` at a $0.01 limit was `accepted` (`asset_class:
us_option`), read back through `get_order`, cancelled through `cancel`, and
read back `canceled`, leaving zero open orders. The unit tests in
`tests/test_cli_broker.py` cover the argv shape, the credential handling and
the error-object parsing without a network.

### The judged session (2026-09-03) — book closed to cash, bot stopped

The hackathon's judged number is total equity at EOD Thursday Sep 3. The
plan for the day — approved before the open and run by a supervisory agent
outside the bot — was a bracket: a protective floor under the book's
mid-marked equity, and failing that, a full sweep to cash mid-afternoon —
because a session that ends with the score has no "later" for a drawdown to
recover into.

The floor fired at 10:33 ET. The watcher (`scripts/bracket_watch.sh`; its
log is `reports/judged_session_bracket.log`) read the book's mid-marked
equity falling from $112,454 to $107,583 in six minutes; on the second
consecutive reading below the $109,500 floor it woke the supervisory
agent, which closed all six positions with limit orders at mid, repriced
once toward the bid. Fills, against a
falling tape: DELL 42.55, NVDA 7.95, UNH 9.10, MS 3.90, INTC 2.36,
UAL 1.72 — $336 of total friction against the trigger reading, with price
improvement on two legs. **Final equity $107,247.11, all cash, +7.25% from
the $100,000 inception in four sessions.** Cash cannot be re-marked, so
that is the judged number whatever the tape did afterwards.

What it did afterwards deserves recording: the drop was the low of a
V-reversal, and an hour later the same six positions marked ~$11,800
higher than where they were sold. Two honest notes on that. The floor was
mis-calibrated — $2,500 of cushion under a book measured the previous
afternoon swinging $5–6k intraday, so it was primed to fire on noise
rather than only on a genuine break. And the giveback it was defending
against is real but unmeasured: the backtests record entry and exit, never
the floating maximum in between, so no rule of this kind currently has
evidence behind it. That measurement (peak-to-exit giveback, trailing-exit
sweeps in `lifecycle.py`) is the first study queued after the competition.

Because the closes were the supervisory agent's, not the bot's, the journal was
reconciled by hand: each of the six rows carries its real Alpaca fill,
order id and timestamp, fees at the bot's own schedule, and
`exit_reason='manual'` so the record says who closed them. The bot was
then stopped (`systemctl stop`) — with the book flat it has nothing to
manage, and a stopped bot cannot open a position into a judged tape. The
status strip shows this as `BOT STOPPED` (muted), a state distinct from
`BOT DOWN` (red): stale heartbeat with zero failed passes means shut down
on purpose, not died.

**Resuming after the competition** means, in order: remove the
`--max-slots 1` drop-in, `systemctl daemon-reload`, `systemctl start
deltaforge-100k-bot`, and restore the Cloudflare Access app from the
backups noted below. None of it should happen by reflex — restarting the
bot is a decision to keep trading the strategy, not a repair.

**Public since 2026-09-02** — the Cloudflare Access app in front of it was
removed for the hackathon judging window (the dashboard is read-only: every
API route is a GET and none can reach an order endpoint). A 200 is the
healthy answer from the public URL. The deleted Access app and its policy
are backed up under `~/.cloudflare/backups/access-deltaforge-*.json` on
GeekForge for restoring after the competition; the pre-change tunnel backup
is `tunnel-ct101-20260830T142019Z.json` in the same place.

The working Cloudflare token is in `homelab-secrets/cloudflare-geekforge.env`.
The one in `cloudflare-dns-tunnel.env` is **revoked** (both the local copy and
the one in the secrets repo) — as is ml30's main `.env` Alpaca pair, on both
hosts.

## Service

The bot runs as `deltaforge-100k-bot.service` on AlgoTrader (unit tracked at
`deploy/deltaforge-100k-bot.service`), enabled so it survives a reboot. It
sleeps between 30-minute bars and only scans while the market is open.

```bash
systemctl status deltaforge-100k-bot
journalctl -u deltaforge-100k-bot -n 50     # or logs-100k/bot.log
systemctl restart deltaforge-100k-bot       # picks up a git pull
```

`deltaforge-bot.service` — the retired $300 instance — is **stopped and
disabled**. Its unit file is still installed on AlgoTrader and still tracked in
`deploy/`, so `systemctl start` would bring back a bot with dead keys. Leave it
alone.

The live unit must be **enabled**, not merely started: a bot launched by hand
with `setsid` dies at the next reboot and the account goes quiet without
anything reporting it.

`Restart=on-failure` with a 30s delay, and `TimeoutStopSec=180` so a stop waits
for the current pass rather than interrupting an order awaiting a fill.

**Foreign-position guard.** If the broker ever reports equity positions this
bot did not open, it logs a `foreign_positions` skip and opens nothing —
reported equity would otherwise count money the buying power does not have.
Written for the borrowed account and kept for the clean one, where it should
never fire; if it does, something else is trading this account.

## Checks

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://deltaforge.geekendzone.net   # 302
ssh root@192.168.68.102 'curl -s localhost:3779/api/snapshot | head -c 300'
ssh root@192.168.68.102 'curl -s localhost:3779/api/health'
ssh root@192.168.68.102 'ps -eo pid,cmd | grep -E "run_paper_bot|next-server" | grep -v grep'

# alive, and exactly one process on the account
ssh root@192.168.68.102 'systemctl is-active deltaforge-100k-bot'
ssh root@192.168.68.102 'grep bot.start /root/repos/deltaforge/logs-100k/bot.log | tail -1'

# the retired instance must stay down
ssh root@192.168.68.102 'systemctl is-active deltaforge-bot; systemctl is-enabled deltaforge-bot'
```

`/api/health` reporting `degraded` with a `401` in its `note` means the
dashboard is authenticating with a revoked key — check `dashboard/.env.local`
against `homelab-secrets/alpaca-deltaforge-100k.env`, then redeploy.

After any tunnel edit, confirm the neighbours too — the sibling dashboard
and `wireguard` routes should answer 200, `screener` and `term` 302.
