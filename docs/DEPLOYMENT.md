# Running DeltaForge

Both halves live on **AlgoTrader (192.168.68.102)**, in `/root/repos/deltaforge`:
the bot writes `data/deltaforge.db` and `logs/events.jsonl`, and the dashboard
reads them from `dashboard/` via `..`. That adjacency is the whole reason they
share a host — the dashboard has no network path to the journal otherwise.

GeekForge (.80) is where this is developed and where the backtests run. It does
not run the bot.

## Account

Alpaca paper **PA3HBSB6VT9C**, nickname "DeltaForge", options trading level 3,
opened 2026-08-30 with $3,000.

It briefly ran against PA35JTJLBB0O, borrowed from the retired
`ml30-paper-bot-v1-5m-frac` service. That was abandoned the same day: the
inherited positions and months of unrelated portfolio history made every
number ambiguous, and a second paper account costs nothing. The old bot stays
stopped and disabled, and its liquidation orders remain queued so that account
closes itself out. Keys:
`homelab-secrets/alpaca-deltaforge.env`, mirrored to
`/root/.secrets/alpaca-deltaforge.env` on AlgoTrader and to
`dashboard/.env.local` (Next reads that at boot — a running dashboard keeps
using an old key until restarted).

Inception is **2026-08-31** at **$3,000.00** — the account's opening balance,
now that its history starts with DeltaForge.

## Bot

```bash
ssh root@192.168.68.102
cd /root/repos/deltaforge
export PATH=$PATH:/root/.local/bin

# one pass, no orders — the safe way to check a change
uv run python scripts/run_paper_bot.py \
    --env-file /root/.secrets/alpaca-deltaforge.env --once --dry-run

# the real thing
uv run python scripts/run_paper_bot.py \
    --env-file /root/.secrets/alpaca-deltaforge.env
```

`--env-file` is required and never inferred. ml30's own settings module carries
a long comment about why: a stray `ALPACA_PAPER_API_KEY` in the environment
once outranked `--env-file` and two bots reported the same account.

Defaults match what the backtest settled on: $300 a position, one slot per $300
of equity capped at 15, 0.55 delta, 7–14 DTE, exit at 5 DTE, and **signals
whose 3R target sits under 5% away are refused**.

Position size stays at **$300 while the account is under $5,000** — the goal
is holding ten positions at once, and $500 on a $3,000 account buys only six
slots. The lever for reaching more names is the universe, not the size.

### The 100k competition instance

A second account runs the **same code and the same strategy** at hackathon
scale: Alpaca paper **PA3YN2XF0XWT**, opened 2026-08-31 with $100,000, keys in
`homelab-secrets/alpaca-deltaforge-100k.env`. It is a second systemd unit
(`deltaforge-100k-bot`, tracked at `deploy/deltaforge-100k-bot.service`) with
its own `data-100k/` and `logs-100k/`, so neither journal can write over the
other. **The $3,000 account keeps running untouched as the control** — if the
two diverge, the difference is sizing, not strategy.

Only two flags differ: `--position-size 7000 --max-slots 14`.

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
so source `alpaca-thetaforge-competition.env` first, not the bot's own key).
It mirrors ml30's `build_broad_liquid_universe.py` — mean per-bar dollar
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

Port **3779** (3777 is ThetaForge, 3778 the ml30 screener — both on this
fleet). The deploy script's kill is **port-scoped on purpose**; `pkill
next-server` would take the neighbours down.

Published at **https://deltaforge.geekendzone.net** through Cloudflare tunnel
CT 101 (`73869032-…`), ingress v183 → `http://192.168.68.102:3779`, with a
proxied CNAME on the zone. Behind **Cloudflare Access** app `deltaforge`
(`08cf2ae1-96f4-4fd3-9ac6-9ff0234e02d0`), 24h session, policy
`Allow_Jose_y_Samary` — the same two email includes as the screener.

**A 302 is the healthy answer** from the public URL: that is the Access login
redirect, not a failure. Pre-change tunnel backup:
`~/.cloudflare/backups/tunnel-ct101-20260830T142019Z.json` on GeekForge.

The working Cloudflare token is in `homelab-secrets/cloudflare-geekforge.env`.
The one in `cloudflare-dns-tunnel.env` is **revoked** (both the local copy and
the one in the secrets repo) — as is ml30's main `.env` Alpaca pair, on both
hosts.

## Service

The bot runs as `deltaforge-bot.service` on AlgoTrader (unit tracked at
`deploy/deltaforge-bot.service`), enabled so it survives a reboot. It sleeps
between 30-minute bars and only scans while the market is open. The 100k
instance is the sibling unit `deltaforge-100k-bot.service`, also enabled.

```bash
systemctl status deltaforge-bot deltaforge-100k-bot
journalctl -u deltaforge-bot -n 50          # or logs/bot.log
systemctl restart deltaforge-bot            # picks up a git pull
```

Both must be **enabled**, not merely started: a bot launched by hand with
`setsid` dies at the next reboot while its sibling comes back, and the two
accounts silently stop being comparable.

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

# both accounts alive, and exactly one process per account
ssh root@192.168.68.102 'systemctl is-active deltaforge-bot deltaforge-100k-bot'
ssh root@192.168.68.102 'grep bot.start /root/repos/deltaforge/logs-100k/bot.log | tail -1'
```

After any tunnel edit, confirm the neighbours too — `thetaforge` and
`wireguard` should answer 200, `screener` and `term` 302.
