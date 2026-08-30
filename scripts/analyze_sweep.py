"""Read a sweep matrix and rank configurations by robustness, not by best cell.

The sweep varies the fill haircut alongside the strategy knobs, and the
real-window run showed fills dominate everything else: a configuration that
only wins at haircut 0 (fills at mid, every time) is a fantasy, not an edge.
So the ranking key is the **worst** result across the haircut axis, and a
configuration only counts as robust when it clears the bar at every haircut
it was tested at.

Ranking uses **profit factor**, not final equity. Final equity compounds
through a 3-slot portfolio whose composition changes with every knob — the
budget filter admits different events, slot collisions resolve differently —
so one lucky early winner can swamp the parameter under test. (The sweep
contains cells where *worse* fills produced four times the equity, which is
mechanically impossible at fixed trade selection.) Profit factor is
per-trade and does not compound, so it measures the knob rather than the
path. Equity is still reported, as scale, not as ranking.

Reports, in order:
  1. Robust configurations (profitable at every haircut), best worst-case first.
  2. The fragile ones — big at haircut 0, dead when you cross the spread.
  3. Marginal effect of each knob, averaged over the rest of the grid.

Usage:
    python scripts/analyze_sweep.py --matrix reports/sweep/sweep_v1_matrix.json
    python scripts/analyze_sweep.py --log reports/sweep/sweep_v1.log   # partial run
"""

from __future__ import annotations

import argparse
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

INITIAL_EQUITY = 3000.0

LOG_RE = re.compile(
    r"delta=(?P<delta>[\d.]+)\s+dte=(?P<lo>\d+)-(?P<hi>\d+)\s+"
    r"final_equity=(?:np\.float64\()?(?P<eq>-?[\d.]+)\)?\s+"
    r"haircut=(?P<haircut>[\d.]+)\s+short_r=(?P<short>[\d.]+|None)\s+"
    r"traded=(?P<traded>\d+)"
)


def cells_from_matrix(path: Path) -> list[dict]:
    return json.loads(path.read_text())["cells"]


def cells_from_log(path: Path) -> list[dict]:
    """Parse the structlog lines of an in-progress run."""
    cells = []
    for line in path.read_text().splitlines():
        m = LOG_RE.search(line)
        if m:
            cells.append(
                {
                    "dte": [int(m["lo"]), int(m["hi"])],
                    "long_delta": float(m["delta"]),
                    "short_at_r": None if m["short"] == "None" else float(m["short"]),
                    "haircut": float(m["haircut"]),
                    "final_equity": float(m["eq"]),
                    "events_traded": int(m["traded"]),
                }
            )
    return cells


def config_key(c: dict) -> tuple:
    return (tuple(c["dte"]), c["long_delta"], c["short_at_r"])


def label(key: tuple) -> str:
    (lo, hi), delta, short = key
    structure = "long call" if short is None else f"spread short@{short:g}R"
    return f"DTE {lo}-{hi}, {delta:.2f}D, {structure}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--matrix", type=Path)
    src.add_argument("--log", type=Path)
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args()

    cells = cells_from_matrix(args.matrix) if args.matrix else cells_from_log(args.log)
    if not cells:
        raise SystemExit("no cells found")

    by_config: dict[tuple, dict[float, dict]] = defaultdict(dict)
    for c in cells:
        by_config[config_key(c)][c["haircut"]] = c

    print(f"{len(cells)} cells, {len(by_config)} configurations\n")

    has_pf = all("profit_factor" in c for cells_ in by_config.values() for c in cells_.values())
    rows = []
    for key, by_haircut in by_config.items():
        equities = {h: c["final_equity"] for h, c in sorted(by_haircut.items())}
        pfs = (
            {h: c["profit_factor"] for h, c in sorted(by_haircut.items())} if has_pf else {}
        )
        worst_pf = min(pfs.values()) if pfs else None
        rows.append(
            {
                "key": key,
                "equities": equities,
                "pfs": pfs,
                "worst_pf": worst_pf,
                "worst_eq": min(equities.values()),
                "best_eq": max(equities.values()),
                "traded": max(c["events_traded"] for c in by_haircut.values()),
                "complete": len(equities) >= 4,
                # Robust = still makes money per trade at every fill quality.
                "robust": (worst_pf > 1.0) if pfs else min(equities.values()) > INITIAL_EQUITY,
            }
        )

    def fmt(r: dict) -> str:
        flag = "" if r["complete"] else "  [partial]"
        if r["pfs"]:
            line = "  ".join(f"h{h:g}: PF {v:.2f}" for h, v in r["pfs"].items())
            head = f"worst PF {r['worst_pf']:.2f}"
        else:
            line = "  ".join(f"h{h:g}=${v:,.0f}" for h, v in r["equities"].items())
            head = f"worst ${r['worst_eq']:>9,.0f}"
        return (
            f"  {label(r['key']):<42} {head}   trades {r['traded']:>4}{flag}\n"
            f"      {line}\n      equity range ${r['worst_eq']:,.0f} - ${r['best_eq']:,.0f}"
        )

    key_fn = (lambda r: -r["worst_pf"]) if has_pf else (lambda r: -r["worst_eq"])
    robust = sorted([r for r in rows if r["robust"]], key=key_fn)
    bar = "PF > 1.0 at every haircut" if has_pf else "beats the starting account"
    print(f"== ROBUST ({len(robust)}): {bar} ==")
    for r in robust[: args.top]:
        print(fmt(r))
    if not robust:
        print("  (none — nothing survives crossing the spread)")

    fragile = sorted(
        [r for r in rows if not r["robust"]],
        key=lambda r: -(max(r["pfs"].values()) if r["pfs"] else r["best_eq"]),
    )
    print(f"\n== FRAGILE ({len(fragile)}): win on good fills, lose on bad ==")
    for r in fragile[:5]:
        print(fmt(r))

    print("\n== MARGINAL EFFECT OF EACH KNOB (median final equity) ==")
    for knob, getter in (
        ("DTE window", lambda c: f"{c['dte'][0]}-{c['dte'][1]}"),
        ("long delta", lambda c: f"{c['long_delta']:.2f}"),
        ("short strike", lambda c: "none (long call)" if c["short_at_r"] is None
         else f"{c['short_at_r']:g}R"),
        ("fill haircut", lambda c: f"{c['haircut']:g}"),
    ):
        buckets: dict[str, list[float]] = defaultdict(list)
        for c in cells:
            buckets[getter(c)].append(c["final_equity"])
        print(f"  {knob}:")
        for k, vals in sorted(buckets.items()):
            print(f"    {k:<18} median ${st.median(vals):>9,.0f}   (n={len(vals)})")


if __name__ == "__main__":
    main()
