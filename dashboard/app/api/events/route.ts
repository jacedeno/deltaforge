import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";

export const dynamic = "force-dynamic";

const LOG = process.env.DF_EVENTS_PATH ?? path.join(process.cwd(), "..", "logs", "events.jsonl");

export async function GET() {
  if (!fs.existsSync(LOG)) return NextResponse.json({ events: [] });
  const lines = fs.readFileSync(LOG, "utf8").trim().split("\n").slice(-150);
  const events = lines
    .map((l) => {
      try {
        return JSON.parse(l);
      } catch {
        return null;
      }
    })
    .filter(Boolean)
    .reverse();
  return NextResponse.json({ events });
}
