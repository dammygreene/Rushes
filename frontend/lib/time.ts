/**
 * "4 minutes ago", "yesterday". Used on the shelves of past searches and saved
 * shots, where the exact minute never matters but the rough age does.
 *
 * Only ever called from data this browser stored itself, which never renders on
 * the server, so there is no clock to disagree with during hydration.
 */

const RELATIVE = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** Each unit with how many of it fit in the next one up. */
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["second", 60],
  ["minute", 60],
  ["hour", 24],
  ["day", 7],
  ["week", 4.35],
  ["month", 12],
];

export function timeAgo(at: number, now: number = Date.now()): string {
  let delta = (at - now) / 1000;
  for (const [unit, span] of UNITS) {
    if (Math.abs(delta) < span) return RELATIVE.format(Math.round(delta), unit);
    delta /= span;
  }
  return RELATIVE.format(Math.round(delta), "year");
}
