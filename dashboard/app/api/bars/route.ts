import { NextResponse } from "next/server";
import { data } from "@/lib/alpaca";

export const dynamic = "force-dynamic";

const TIMEFRAMES = new Set(["5Min", "15Min", "30Min", "1Hour", "1Day"]);
const SYMBOL = /^[A-Z.]{1,10}$/;

// Alpaca caps a single page at 10,000 bars and hands back a token for the
// rest. Six pages covers any window the chart asks for; without the loop the
// response silently stopped at the *oldest* 2,000 bars, so a 5-minute chart
// over a long trade lost its most recent candles rather than its oldest.
const MAX_PAGES = 6;

type RawBar = { t: string; o: number; h: number; l: number; c: number };

/**
 * Underlying bars for the trade charts. IEX, matching the feed the bot reads —
 * a chart drawn on the consolidated tape would show highs and lows the strategy
 * never acted on, and every stop/target marker would look subtly wrong.
 */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") ?? "").toUpperCase();
  const tf = url.searchParams.get("tf") ?? "30Min";
  const from = url.searchParams.get("from");
  const to = url.searchParams.get("to");

  if (!SYMBOL.test(symbol)) return NextResponse.json({ error: "bad symbol" }, { status: 400 });
  if (!TIMEFRAMES.has(tf)) return NextResponse.json({ error: "bad timeframe" }, { status: 400 });

  try {
    const bars: { t: number; o: number; h: number; l: number; c: number }[] = [];
    let pageToken: string | undefined;

    for (let page = 0; page < MAX_PAGES; page++) {
      const q = new URLSearchParams({ timeframe: tf, feed: "iex", limit: "10000" });
      if (from) q.set("start", from);
      if (to) q.set("end", to);
      if (pageToken) q.set("page_token", pageToken);

      const r = await data(`/v2/stocks/${symbol}/bars?${q}`);
      for (const b of (r.bars ?? []) as RawBar[]) {
        bars.push({
          t: Math.floor(Date.parse(b.t) / 1000),
          o: b.o, h: b.h, l: b.l, c: b.c,
        });
      }
      pageToken = r.next_page_token ?? undefined;
      if (!pageToken) break;
    }

    return NextResponse.json({ symbol, tf, bars });
  } catch (err) {
    return NextResponse.json({ error: String(err).slice(0, 300) }, { status: 500 });
  }
}
