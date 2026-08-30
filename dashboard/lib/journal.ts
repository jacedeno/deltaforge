import path from "node:path";
import fs from "node:fs";
import Database from "better-sqlite3";

/**
 * Read-only access to the bot's journal.
 *
 * The dashboard runs with cwd = <repo>/dashboard, so `..` is the bot's root —
 * the same convention ThetaForge uses. Opened read-only against a WAL database,
 * so reads never block the bot's writes and the page can never corrupt them.
 */
const DB_PATH = process.env.DF_DB_PATH ?? path.join(process.cwd(), "..", "data", "deltaforge.db");

export type TradeRow = {
  id: number;
  status: string;
  symbol: string;
  occ: string;
  strike: number;
  expiry: string;
  dte_at_entry: number;
  delta_at_entry: number | null;
  signal_ts: string;
  entry_price: number;
  stop_price: number;
  target_price: number;
  risk_per_share: number;
  contracts: number;
  limit_price: number | null;
  entry_fill: number | null;
  entry_ts: string | null;
  debit: number | null;
  fees: number;
  exit_ts: string | null;
  exit_limit: number | null;
  exit_fill: number | null;
  exit_reason: string | null;
  underlying_at_exit: number | null;
  pnl: number | null;
};

export type FillRow = {
  trade_id: number;
  order_id: string;
  side: string;
  qty: number;
  price: number;
  filled_at: string;
  leg: string;
};

function open(): Database.Database | null {
  if (!fs.existsSync(DB_PATH)) return null;
  return new Database(DB_PATH, { readonly: true, fileMustExist: true });
}

export function readTrades(limit = 300): { trades: TradeRow[]; ready: boolean } {
  const db = open();
  if (!db) return { trades: [], ready: false };
  try {
    const rows = db
      .prepare("SELECT * FROM trades ORDER BY COALESCE(entry_ts, signal_ts) DESC LIMIT ?")
      .all(limit) as TradeRow[];
    return { trades: rows, ready: true };
  } finally {
    db.close();
  }
}

export function readFills(tradeIds: number[]): Record<number, FillRow[]> {
  const db = open();
  if (!db || tradeIds.length === 0) return {};
  try {
    const q = db.prepare(
      `SELECT * FROM fills WHERE trade_id IN (${tradeIds.map(() => "?").join(",")}) ORDER BY filled_at`,
    );
    const out: Record<number, FillRow[]> = {};
    for (const f of q.all(...tradeIds) as FillRow[]) (out[f.trade_id] ??= []).push(f);
    return out;
  } finally {
    db.close();
  }
}

/** Stats over closed trades. Aborted entries are excluded from P&L but counted. */
export function summarise(trades: TradeRow[]) {
  const closed = trades.filter((t) => t.status === "closed" && t.pnl != null);
  const open = trades.filter((t) => t.status === "open");
  const aborted = trades.filter((t) => t.status === "aborted");
  if (closed.length === 0) {
    return {
      closed: 0, open: open.length, aborted: aborted.length,
      totalPnl: 0, winRate: 0, profitFactor: 0, avgWin: 0, avgLoss: 0, avgSlippage: null,
    };
  }
  const pnl = closed.map((t) => t.pnl as number);
  const wins = pnl.filter((p) => p > 0);
  const losses = pnl.filter((p) => p < 0).map((p) => -p);
  const slip = closed
    .filter((t) => t.limit_price != null && t.entry_fill != null)
    .map((t) => (t.entry_fill as number) - (t.limit_price as number));
  return {
    closed: closed.length,
    open: open.length,
    aborted: aborted.length,
    totalPnl: pnl.reduce((a, b) => a + b, 0),
    winRate: wins.length / closed.length,
    profitFactor: losses.length
      ? wins.reduce((a, b) => a + b, 0) / losses.reduce((a, b) => a + b, 0)
      : Infinity,
    avgWin: wins.length ? wins.reduce((a, b) => a + b, 0) / wins.length : 0,
    avgLoss: losses.length ? -losses.reduce((a, b) => a + b, 0) / losses.length : 0,
    // Cents paid above the limit the bot asked for — the fill assumption made visible.
    avgSlippage: slip.length ? slip.reduce((a, b) => a + b, 0) / slip.length : null,
  };
}
