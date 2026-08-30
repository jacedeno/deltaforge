import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

const HEARTBEAT =
  process.env.DF_HEARTBEAT_PATH ?? path.join(process.cwd(), "..", "data", "heartbeat.json");

/** The bot writes a heartbeat every pass; a 30-minute strategy beats slowly. */
const STALE_AFTER_S = 45 * 60;

export async function GET() {
  if (!fs.existsSync(HEARTBEAT)) {
    return NextResponse.json({ alive: false, degraded: false, note: "no heartbeat yet" });
  }
  try {
    const hb = JSON.parse(fs.readFileSync(HEARTBEAT, "utf8"));
    const ageS = (Date.now() - Date.parse(hb.ts)) / 1000;
    return NextResponse.json({
      alive: ageS < STALE_AFTER_S,
      degraded: (hb.consecutive_failures ?? 0) >= 2,
      ageSeconds: Math.round(ageS),
      failures: hb.consecutive_failures ?? 0,
      lastScan: hb.last_scan ?? null,
      uptimeSeconds: hb.uptime_seconds ?? 0,
      note: hb.note ?? "",
    });
  } catch (err) {
    return NextResponse.json({ alive: false, degraded: true, note: String(err).slice(0, 150) });
  }
}
