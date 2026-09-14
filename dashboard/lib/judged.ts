/**
 * The hackathon window: the sessions the Alpaca AI Trading Agents Hackathon
 * actually measured, 2026-08-31 through the close of Thursday 2026-09-03.
 *
 * This exists because the account did not stop when the competition did. The
 * bot kept trading afterwards, so "what the account holds now" and "what the
 * judges were shown" drifted apart within a week. Both are true, and the page
 * would be lying by omission if it showed only one of them: the live number
 * without its date reads as the hackathon result, and the hackathon result
 * without its date reads as today's balance.
 *
 * So the window is pinned here, once, and every judged figure is derived from
 * the record inside it — Alpaca's own portfolio history and the bot's journal.
 * Nothing on the judged view is a constant that was typed in from a
 * screenshot; the only constants are the two dates below.
 */
export const JUDGED_START = "2026-08-31";

/** Thursday's close. The competition measured equity end-of-day here. */
export const JUDGED_END = "2026-09-03";

/** 16:00 at the exchange on the judged day, as an epoch millisecond. */
export const JUDGED_CLOSE_MS = Date.parse(`${JUDGED_END}T16:00:00-04:00`);

/**
 * The `end` to ask Alpaca for, which is the day *after* the judged close.
 *
 * Portfolio history treats `end` as exclusive: asking for the judged day
 * itself returns the window up to the previous session and drops the very
 * close the hackathon was measured on. Asking for one day more and clipping at
 * `JUDGED_CLOSE_MS` is what puts the Thursday close back in the series.
 */
export const JUDGED_FETCH_END = new Date(JUDGED_CLOSE_MS + 86_400_000)
  .toISOString()
  .slice(0, 10);

/** `true` while `ts` (an ISO string from the journal) falls inside the window. */
export function inJudgedWindow(ts: string | null): boolean {
  if (!ts) return false;
  const ms = Date.parse(ts);
  return Number.isFinite(ms) && ms >= Date.parse(`${JUDGED_START}T00:00:00-04:00`) && ms <= JUDGED_CLOSE_MS;
}
