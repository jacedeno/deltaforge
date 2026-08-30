import { NextResponse } from "next/server";
import { optionQuotes, spots, trading } from "@/lib/alpaca";
import { readTrades } from "@/lib/journal";
import { INCEPTION_EQUITY } from "@/lib/inception";

export const dynamic = "force-dynamic";

/**
 * The hub: account, clock, and every open position priced at the live mid.
 *
 * Open positions come from the journal, not from the broker, because the
 * journal is what carries the signal levels the position was opened on. The
 * broker is consulted only for what it alone knows — the current quote.
 */
export async function GET() {
  try {
    const [account, clock] = await Promise.all([
      trading("/v2/account"),
      trading("/v2/clock"),
    ]);

    const { trades, ready } = readTrades(300);
    const open = trades.filter((t) => t.status === "open");
    const [quotes, underlying] = await Promise.all([
      optionQuotes(open.map((t) => t.occ)),
      spots([...new Set(open.map((t) => t.symbol))]),
    ]);

    const positions = open.map((t) => {
      const q = quotes[t.occ];
      const mid = q ? (q.bp + q.ap) / 2 : null;
      const entry = t.entry_fill ?? 0;
      const spot = underlying[t.symbol] ?? null;
      return {
        id: t.id,
        symbol: t.symbol,
        occ: t.occ,
        strike: t.strike,
        expiry: t.expiry,
        contracts: t.contracts,
        entryFill: entry,
        limitPrice: t.limit_price,
        debit: t.debit,
        deltaAtEntry: t.delta_at_entry,
        signalTs: t.signal_ts,
        levels: {
          entry: t.entry_price,
          stop: t.stop_price,
          target: t.target_price,
        },
        spot,
        bid: q?.bp ?? null,
        ask: q?.ap ?? null,
        mid,
        // Live P&L at the mid — the honest mark for a position you could close now.
        plAtMid: mid == null ? null : (mid - entry) * 100 * t.contracts,
        plPctOfDebit:
          mid == null || !t.debit ? null : ((mid - entry) * 100 * t.contracts) / t.debit * 100,
        breakeven: t.strike + entry,
        daysToExpiry: Math.ceil(
          (Date.parse(`${t.expiry}T20:00:00Z`) - Date.now()) / 86_400_000,
        ),
      };
    });

    const equity = Number(account.equity);
    return NextResponse.json({
      asOf: new Date().toISOString(),
      journalReady: ready,
      market: { isOpen: clock.is_open, nextOpen: clock.next_open, nextClose: clock.next_close },
      account: {
        number: account.account_number,
        equity,
        cash: Number(account.cash),
        optionsBuyingPower: Number(account.options_buying_power ?? account.buying_power),
        inceptionEquity: INCEPTION_EQUITY,
        pnlSinceInception: equity - INCEPTION_EQUITY,
      },
      positions,
      deployed: positions.reduce((a, p) => a + (p.debit ?? 0), 0),
    });
  } catch (err) {
    return NextResponse.json({ error: String(err).slice(0, 300) }, { status: 500 });
  }
}
