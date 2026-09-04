#!/bin/bash
# Bracket watch for the judged session (2026-09-03) — verbatim as it ran.
#
# The protective floor that closed the book to cash on judging day. It ran
# OUTSIDE the trading bot, under a plan approved before the open, and it
# only watches: when an arm fires it exits and wakes the supervisory agent,
# which placed the six sell_to_close limit orders at mid (repriced once
# toward the bid) through the Trading API. The bot itself knows only the
# stop / target / DTE exits. Run log: reports/judged_session_bracket.log
#
#   FLOOR  - equity-at-mid < $109,500 on two consecutive readings
#   WINDOW - 14:30 ET reached: time for the planned sweep to cash
LOG=${LOG:-./bracket.log}FLOOR=109500
BELOW=0
echo "$(date -Is) bracket armed: floor=$FLOOR sweep=14:30ET" >> "$LOG"
while true; do
  HHMM=$(TZ=America/New_York date +%H%M)
  if [ "$HHMM" -ge 1430 ]; then
    echo "$(date -Is) WINDOW reached at $HHMM ET" >> "$LOG"; echo "WINDOW"; exit 0
  fi
  V=$(ssh -o ConnectTimeout=10 root@192.168.68.102 'set -a; . /root/.secrets/alpaca-deltaforge-100k.env; set +a
    H1="APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY"; H2="APCA-API-SECRET-KEY: $ALPACA_PAPER_SECRET"
    curl -s -m 15 -H "$H1" -H "$H2" "$ALPACA_PAPER_ENDPOINT/v2/account" > /tmp/bw_a.json
    curl -s -m 15 -H "$H1" -H "$H2" "$ALPACA_PAPER_ENDPOINT/v2/positions" > /tmp/bw_p.json
    SY=$(python3 -c "import json;print(\",\".join(p[\"symbol\"] for p in json.load(open(\"/tmp/bw_p.json\"))))" 2>/dev/null)
    [ -n "$SY" ] && curl -s -m 15 -H "$H1" -H "$H2" "https://data.alpaca.markets/v1beta1/options/quotes/latest?symbols=$SY" > /tmp/bw_q.json
    python3 - <<PY
import json
try:
    a=json.load(open("/tmp/bw_a.json")); ps=json.load(open("/tmp/bw_p.json"))
    q=json.load(open("/tmp/bw_q.json")).get("quotes",{}) if ps else {}
    cash=float(a["cash"]); mv=0; bad=0
    for p in ps:
        Q=q.get(p["symbol"])
        if not Q or not Q.get("bp") or not Q.get("ap"): bad+=1; mv+=float(p["market_value"]); continue
        mv+=int(p["qty"])*((Q["bp"]+Q["ap"])/2)*100
    print("%d %d %d %d"%(cash+mv, float(a["equity"]), len(ps), bad))
except Exception as e:
    print("ERR", str(e)[:60])
PY' 2>/dev/null)
  set -- $V
  if [ "$1" = "ERR" ] || [ -z "$1" ]; then
    echo "$(date -Is) reading failed: $V" >> "$LOG"
  else
    EQMID=$1; EQMARK=$2; NPOS=$3; BADQ=$4
    echo "$(date -Is) $HHMM ET  eq_mid=$EQMID eq_mark=$EQMARK pos=$NPOS badq=$BADQ below=$BELOW" >> "$LOG"
    if [ "$NPOS" -eq 0 ]; then echo "$(date -Is) book flat" >> "$LOG"; echo "FLAT"; exit 0; fi
    if [ "$EQMID" -lt "$FLOOR" ] && [ "$BADQ" -eq 0 ]; then
      BELOW=$((BELOW+1))
      if [ "$BELOW" -ge 2 ]; then echo "$(date -Is) FLOOR breached: $EQMID" >> "$LOG"; echo "FLOOR $EQMID"; exit 0; fi
    else
      BELOW=0
    fi
  fi
  sleep 75
done
