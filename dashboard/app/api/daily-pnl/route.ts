import { NextResponse } from "next/server";
import { trading } from "@/lib/alpaca";
import { INCEPTION_DATE } from "@/lib/inception";

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

    return NextResponse.json({ days: days.slice(-10) });
  } catch (err) {
    return NextResponse.json({ error: String(err).slice(0, 300) }, { status: 500 });
  }
}
