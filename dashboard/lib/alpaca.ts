const TRADING = "https://paper-api.alpaca.markets";
const DATA = "https://data.alpaca.markets";

function headers() {
  const key = process.env.ALPACA_PAPER_API_KEY;
  const secret = process.env.ALPACA_PAPER_SECRET;
  if (!key || !secret) throw new Error("ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET not set");
  return { "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret };
}

async function get(base: string, path: string) {
  const res = await fetch(`${base}${path}`, { headers: headers(), cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status} ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

export const trading = (path: string) => get(TRADING, path);
export const data = (path: string) => get(DATA, path);

/** Latest option quotes, keyed by OCC symbol. */
export async function optionQuotes(occ: string[]): Promise<Record<string, { bp: number; ap: number }>> {
  if (occ.length === 0) return {};
  const r = await data(`/v1beta1/options/quotes/latest?symbols=${occ.join(",")}`);
  const out: Record<string, { bp: number; ap: number }> = {};
  for (const [sym, q] of Object.entries(r.quotes ?? {})) {
    const quote = q as { bp?: number; ap?: number };
    if (quote.bp != null && quote.ap != null) out[sym] = { bp: quote.bp, ap: quote.ap };
  }
  return out;
}

/** Latest underlying trades, keyed by symbol. IEX matches what the bot reads. */
export async function spots(symbols: string[]): Promise<Record<string, number>> {
  if (symbols.length === 0) return {};
  const r = await data(`/v2/stocks/trades/latest?symbols=${symbols.join(",")}&feed=iex`);
  const out: Record<string, number> = {};
  for (const [sym, t] of Object.entries(r.trades ?? {})) {
    const trade = t as { p?: number };
    if (trade.p != null) out[sym] = trade.p;
  }
  return out;
}
