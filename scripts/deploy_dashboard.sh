#!/usr/bin/env bash
# DeltaForge dashboard — build and (re)start on AlgoTrader, port 3779.
#
# Runs beside the bot so `..` reaches its journal and event log, the same
# convention ThetaForge uses. Published at deltaforge.geekendzone.net through
# the CT 101 Cloudflare tunnel, behind Cloudflare Access.
#
# The kill is PORT-scoped on purpose — never `pkill next-server`. Other Next
# apps share this fleet (ThetaForge 3777, ml30-screener 3778) and a broad kill
# would take them down with it.
set -euo pipefail

PORT=3779
cd "$(dirname "$0")/../dashboard"

if [ ! -f .env.local ]; then
  echo "missing dashboard/.env.local — copy the keys from ~/.secrets/alpaca-deltaforge.env" >&2
  exit 1
fi

npm install --silent
npm run build

pid=$(ss -ltnp 2>/dev/null | grep ":${PORT}" | grep -oP 'pid=\K[0-9]+' | head -1 || true)
if [ -n "${pid:-}" ]; then
  echo "stopping existing dashboard (pid ${pid})"
  kill "$pid"
  sleep 1
fi

setsid nohup npm run start -- -p "$PORT" >/dev/null 2>&1 </dev/null &
sleep 4

if curl -fsS "http://127.0.0.1:${PORT}/" -o /dev/null; then
  echo "dashboard up on :${PORT}"
else
  echo "dashboard did not answer on :${PORT}" >&2
  exit 1
fi
