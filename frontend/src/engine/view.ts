/** Pure helpers for drawing and picking. No DOM, no Pixi: easy to test. */

export { PEOPLE as ACTIVITY_COLORS } from "./art";

export const hex = (c: number) => `#${c.toString(16).padStart(6, "0")}`;

/** Index of the nearest point to (x, y) within radius, or -1. Linear scan: a few thousand points is microseconds. */
export function nearestPoint(xs: ArrayLike<number>, ys: ArrayLike<number>, x: number, y: number, radius: number): number {
  let best = -1;
  let bestD = radius * radius;
  for (let i = 0; i < xs.length; i++) {
    const dx = xs[i] - x;
    const dy = ys[i] - y;
    const d = dx * dx + dy * dy;
    if (d <= bestD) {
      best = i;
      bestD = d;
    }
  }
  return best;
}

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export function rectAt<T extends Rect>(rects: T[], x: number, y: number): T | undefined {
  return rects.find((r) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h);
}

/** Interpolate positions between two frames so movement looks smooth between server ticks. */
export function lerpFrames(
  prev: { ids: number[]; x: number[]; y: number[] },
  next: { ids: number[]; x: number[]; y: number[] },
  f: number,
  out: { x: Float32Array; y: Float32Array },
): void {
  const index = new Map<number, number>();
  prev.ids.forEach((id, i) => index.set(id, i));
  for (let i = 0; i < next.ids.length; i++) {
    const j = index.get(next.ids[i]);
    if (j === undefined) {
      out.x[i] = next.x[i];
      out.y[i] = next.y[i];
    } else {
      out.x[i] = prev.x[j] + (next.x[i] - prev.x[j]) * f;
      out.y[i] = prev.y[j] + (next.y[i] - prev.y[j]) * f;
    }
  }
}

export const SPEEDS: { label: string; value: number }[] = [
  { label: "1 min/s", value: 1 },
  { label: "10 min/s", value: 10 },
  { label: "1 h/s", value: 60 },
  { label: "6 h/s", value: 360 },
  { label: "1 day/s", value: 1440 },
];

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const EPOCH = Date.UTC(2026, 0, 1);

/** A simulation minute in words, the same way the city writes it ("Fri 02 Jan 2026 10:00"). */
export function simLabel(t: number): string {
  const d = new Date(EPOCH + t * 60_000);
  const day = Math.floor(t / 1440);
  const two = (n: number) => String(n).padStart(2, "0");
  return `${WEEKDAYS[(day + 3) % 7]} ${two(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()} ${two(d.getUTCHours())}:${two(d.getUTCMinutes())}`;
}

/** How far back a moment is, in plain words. */
export function agoLabel(minutes: number): string {
  if (minutes < 60) return `${Math.round(minutes)} min ago`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} h ago`;
  const days = Math.round(minutes / 1440);
  return days === 1 ? "a day ago" : `${days} days ago`;
}
