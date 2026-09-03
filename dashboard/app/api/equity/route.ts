import { NextResponse } from "next/server";
import { trading } from "@/lib/alpaca";
import { INCEPTION_EQUITY, nyDay, sinceInception } from "@/lib/inception";

export const dynamic = "force-dynamic";

// The finest resolution Alpaca serves at each span: minute bars for a day,
// five-minute for a week (~395 points), and daily beyond that — the API
// refuses intraday timeframes past 30 days.
const RANGES: Record<string, { period: string; timeframe: string }> = {
  "1D": { period: "1D", timeframe: "1Min" },
  "1W": { period: "1W", timeframe: "5Min" },
  "1M": { period: "1M", timeframe: "1D" },
  ALL: { period: "3M", timeframe: "1D" },
};

/**
 * The equity curve, always measured from inception.
 *
 * Alpaca's portfolio history covers the account, which predates DeltaForge by
 * months of a retired bot's trading. Anything before inception is dropped and
 * the series is anchored at the opening balance, so the curve answers "how is
 * DeltaForge doing" rather than "what has this account ever done".
 */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const requested = (url.searchParams.get("range") ?? "1W").toUpperCase();
  const order = ["ALL", "1M", "1W", "1D"];
  const start = order.includes(requested) ? order.indexOf(requested) : 2;

  try {
    // Cascade to shorter ranges until one has more than a single point — a
    // brand-new record otherwise renders an empty chart on every range.
    for (let i = start; i < order.length; i++) {
      const key = order[i];
      const { period, timeframe } = RANGES[key];
      const h = await trading(
        `/v2/account/portfolio/history?period=${period}&timeframe=${timeframe}&intraday_reporting=market_hours`,
      );
      const { t, equity } = sinceInception(h.timestamp ?? [], h.equity ?? []);
      if (t.length > 1) {
        const points = t.map((ts, j) => ({ t: ts * 1000, equity: equity[j] }));
        // The curve must end where the header's equity is. History lags the
        // account two ways: the daily series only gains today's row once it
        // settles, and the intraday series stops at the closing bar while the
        // account goes on being re-marked at the closing bids.
        //
        // Correcting the last bar in place rather than appending is what keeps
        // the curve inside market hours — an extra point stamped `now` sat
        // hours past the close and drew a long flat tail across dead time.
        const last = points[points.length - 1];
        if (Date.now() - last.t > 10 * 60_000) {
          const live = Number((await trading("/v2/account")).equity);
          if (Number.isFinite(live) && live > 0) {
            if (nyDay(last.t) === nyDay(Date.now())) last.equity = live;
            else points.push({ t: Date.now(), equity: live });
          }
        }
        return NextResponse.json({
          range: key,
          fellBack: key !== requested,
          points,
          inceptionEquity: INCEPTION_EQUITY,
        });
      }
    }
    return NextResponse.json({
      range: requested, fellBack: false, points: [], inceptionEquity: INCEPTION_EQUITY,
      note: "the curve starts once DeltaForge has traded",
    });
  } catch (err) {
    return NextResponse.json({ error: String(err).slice(0, 300) }, { status: 500 });
  }
}
