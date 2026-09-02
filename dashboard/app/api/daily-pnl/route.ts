import { NextResponse } from "next/server";
import { trading } from "@/lib/alpaca";
import { INCEPTION_DATE, nyDay } from "@/lib/inception";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const h = await trading(
      "/v2/account/portfolio/history?period=1M&timeframe=1D&intraday_reporting=market_hours",
    );
    const startMs = Date.parse(`${INCEPTION_DATE}T00:00:00-04:00`);
    const ts: number[] = h.timestamp ?? [];
    const pl: (number | null)[] = h.profit_loss ?? [];

    const days = ts
      .map((t, i) => ({ t: t * 1000, pnl: pl[i] ?? 0 }))
      .filter((d) => d.t >= startMs);

    // Today's row only appears once the day settles, so the bar for the
    // session that just closed was missing. `last_equity` is the previous
    // trading day's close, which makes the difference exactly today's P&L.
    if (days.length === 0 || nyDay(days[days.length - 1].t) !== nyDay(Date.now())) {
      const a = await trading("/v2/account");
      const now = Number(a.equity);
      const prev = Number(a.last_equity);
      if (Number.isFinite(now) && Number.isFinite(prev) && prev > 0) {
        days.push({ t: Date.now(), pnl: now - prev });
      }
    }

    return NextResponse.json({ days: days.slice(-10) });
  } catch (err) {
    return NextResponse.json({ error: String(err).slice(0, 300) }, { status: 500 });
  }
}
