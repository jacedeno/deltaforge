# Running DeltaForge

Both halves live on **AlgoTrader (192.168.68.102)**, in `/root/repos/deltaforge`:
the bot writes `data/deltaforge.db` and `logs/events.jsonl`, and the dashboard
reads them from `dashboard/` via `..`. That adjacency is the whole reason they
share a host — the dashboard has no network path to the journal otherwise.

GeekForge (.80) is where this is developed and where the backtests run. It does
not run the bot.

## Account

Alpaca paper **PA35JTJLBB0O**, options trading level 3. Reassigned on
2026-08-30 from the retired `ml30-paper-bot-v1-5m-frac` service, which was
stopped, disabled, and its 39 positions liquidated first. Keys:
`homelab-secrets/alpaca-deltaforge.env`, mirrored to
`/root/.secrets/alpaca-deltaforge.env` on AlgoTrader and to
`dashboard/.env.local` (Next reads that at boot — a running dashboard keeps
using an old key until restarted).

Inception is **2026-08-31** at **$3,030.85**. Everything the dashboard reports
is measured from there, because the account's own history belongs to the bot
that used to own it.

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
between 30-minute bars and only scans while the market is open.

```bash
systemctl status deltaforge-bot
journalctl -u deltaforge-bot -n 50          # or logs/bot.log
systemctl restart deltaforge-bot            # picks up a git pull
```

`Restart=on-failure` with a 30s delay, and `TimeoutStopSec=180` so a stop waits
for the current pass rather than interrupting an order awaiting a fill.

**First-open guard.** While the account still holds equity positions from the
strategy it was handed over from, the bot logs a `foreign_positions` skip and
opens nothing — reported equity would otherwise count money the buying power
does not have. It manages its own positions normally throughout. The guard
clears itself once those liquidations fill.

## Checks

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://deltaforge.geekendzone.net   # 302
ssh root@192.168.68.102 'curl -s localhost:3779/api/snapshot | head -c 300'
ssh root@192.168.68.102 'curl -s localhost:3779/api/health'
ssh root@192.168.68.102 'ps -eo pid,cmd | grep -E "run_paper_bot|next-server" | grep -v grep'
```

After any tunnel edit, confirm the neighbours too — `thetaforge` and
`wireguard` should answer 200, `screener` and `term` 302.
