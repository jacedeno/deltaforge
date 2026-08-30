import { NextResponse } from "next/server";
import { readFills, readTrades, summarise } from "@/lib/journal";

export const dynamic = "force-dynamic";

export async function GET() {
  const { trades, ready } = readTrades(300);
  if (!ready) {
    return NextResponse.json({
      trades: [], fills: {}, stats: null,
      note: "journal not initialised yet — the bot writes it on its first pass",
    });
  }
  const fills = readFills(trades.map((t) => t.id));
  return NextResponse.json({ trades, fills, stats: summarise(trades) });
}
