#!/usr/bin/env bash
# DeltaForge dashboard — build and (re)start on AlgoTrader, port 3779.
#
# Runs beside the bot so `..` reaches its journal and event log. Published
# at deltaforge.geekendzone.net through
# the CT 101 Cloudflare tunnel, behind Cloudflare Access.
#
# The server itself runs as deltaforge-dashboard.service (unit tracked in
# deploy/), so this script builds and then restarts the unit. It used to kill
# whatever held the port and relaunch with setsid, which raced the unit's own
# Restart= and left a process systemd did not know about.
set -euo pipefail

PORT=3779
cd "$(dirname "$0")/../dashboard"

if [ ! -f .env.local ]; then
  echo "missing dashboard/.env.local — see docs/DEPLOYMENT.md, keys from ~/.secrets/alpaca-deltaforge-paper.env" >&2
  exit 1
fi

# ci, not install: install rewrites package-lock.json on this host (its npm
# drops the libc fields), which left the deploy checkout dirty.
npm ci --silent
npm run build

systemctl restart deltaforge-dashboard

for _ in $(seq 20); do
  if curl -fsS "http://127.0.0.1:${PORT}/" -o /dev/null 2>&1; then
    acct=$(curl -fsS "http://127.0.0.1:${PORT}/api/snapshot" | grep -oP '"number":"\K[^"]+' || true)
    echo "dashboard up on :${PORT}, account ${acct:-unknown}"
    exit 0
  fi
  sleep 1
done
echo "dashboard did not answer on :${PORT} — journalctl -u deltaforge-dashboard -n 50" >&2
exit 1
