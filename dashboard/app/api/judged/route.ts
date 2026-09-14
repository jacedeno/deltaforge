import { NextResponse } from "next/server";
import { trading } from "@/lib/alpaca";
import { readTrades, summarise } from "@/lib/journal";
import { INCEPTION_EQUITY } from "@/lib/inception";
import {
  JUDGED_CLOSE_MS, JUDGED_END, JUDGED_FETCH_END, JUDGED_START, inJudgedWindow,
} from "@/lib/judged";

export const dynamic = "force-dynamic";

/**
 * The judged week, exactly as it stood when the hackathon closed.
 *
 * Both halves come from the record rather than from memory: the curve is
 * Alpaca's portfolio history bounded to the window, and the trades are the
 * journal rows the bot wrote as it opened and closed them. The five-minute
 * series is what the submission was measured on, and it is still inside
 * Alpaca's 30-day intraday retention; past that the daily series is the only
 * thing left, so the fallback below keeps the view alive rather than blank.
 *
 * Unlike /api/equity, nothing here is re-marked to the live account. The
 * window is closed. Its last point is its last point.
 */
export async function GET() {
  try {
    const intraday = await trading(
      `/v2/account/portfolio/history?start=${JUDGED_START}&end=${JUDGED_FETCH_END}` +
        `&timeframe=5Min&intraday_reporting=market_hours`,
    ).catch(() => null);

    let ts: number[] = intraday?.timestamp ?? [];
    let eq: (number | null)[] = intraday?.equity ?? [];
    let resolution = "5Min";

    if (ts.length < 2) {
      const daily = await trading(
        `/v2/account/portfolio/history?start=${JUDGED_START}&end=${JUDGED_FETCH_END}&timeframe=1D`,
      );
      ts = daily.timestamp ?? [];
      eq = daily.equity ?? [];
      resolution = "1D";
    }

    // Alpaca reports the hours before the account was funded as an equity of
    // zero; kept, they draw a curve leaping from nothing to $100,000.
    const points: { t: number; equity: number }[] = [];
    for (let i = 0; i < ts.length; i++) {
      const v = eq[i];
      const ms = ts[i] * 1000;
      if (v == null || v <= 0 || ms > JUDGED_CLOSE_MS) continue;
      points.push({ t: ms, equity: v });
    }

    const closeEquity = points.length ? points[points.length - 1].equity : null;

    const { trades, ready } = readTrades(300);
    // Entered inside the window. The book was closed to cash on the judged
    // day, so every one of these also exits inside it.
    const judged = trades
      .filter((t) => inJudgedWindow(t.entry_ts) && t.status === "closed")
      .sort((a, b) => Date.parse(a.entry_ts ?? "") - Date.parse(b.entry_ts ?? ""));

    return NextResponse.json({
      window: { start: JUDGED_START, end: JUDGED_END, closedAt: new Date(JUDGED_CLOSE_MS).toISOString() },
      resolution,
      journalReady: ready,
      inceptionEquity: INCEPTION_EQUITY,
      closeEquity,
      pnl: closeEquity == null ? null : closeEquity - INCEPTION_EQUITY,
      pnlPct: closeEquity == null ? null : ((closeEquity - INCEPTION_EQUITY) / INCEPTION_EQUITY) * 100,
      points,
      trades: judged.map((t) => ({
        id: t.id,
        symbol: t.symbol,
        occ: t.occ,
        strike: t.strike,
        expiry: t.expiry,
        contracts: t.contracts,
        entryTs: t.entry_ts,
        exitTs: t.exit_ts,
        entryFill: t.entry_fill,
        exitFill: t.exit_fill,
        debit: t.debit,
        exitReason: t.exit_reason,
        deltaAtEntry: t.delta_at_entry,
        pnl: t.pnl,
        pnlPctOfDebit: t.pnl == null || !t.debit ? null : (t.pnl / t.debit) * 100,
      })),
      stats: summarise(judged),
    });
  } catch (err) {
    return NextResponse.json({ error: String(err).slice(0, 300) }, { status: 500 });
  }
}
