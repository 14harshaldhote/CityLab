/** Pure helpers for drawing and picking. No DOM, no Pixi: easy to test. */

export const ACTIVITY_COLORS = [
  0x6c7a96, // sleeping
  0x9c8f7a, // at home
  0xd59a3a, // eating at home
  0xe2723b, // eating out
  0x2f7fb0, // working
  0x8a5cc4, // at school
  0xd4508a, // visiting friends
  0x3a9a55, // at the park
  0xc9b13a, // shopping
  0x1d2a24, // travelling
];

export const BUILDING_COLORS: Record<string, number> = {
  home: 0xe9dcc5,
  office: 0xb9c8d8,
  shop: 0xf0c987,
  restaurant: 0xeeb0a0,
  factory: 0xc2bdb4,
  school: 0xd8c4ec,
  hospital: 0xf4b6b6,
  police: 0xa9b8e6,
  city_hall: 0xe8d58f,
  bank: 0xb7dcc0,
  park: 0xa9d59a,
  bus_depot: 0xc8c8c8,
};

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

/** How dark the streets are: 0 at full daylight, ~0.6 at deep night. */
export function nightShade(sunElevationDeg: number, cloudPct: number): number {
  const light = Math.min(1, Math.max(0, (sunElevationDeg + 8) / 16));
  return Math.min(0.62, (1 - light) * 0.62 + (cloudPct / 100) * 0.08 * light);
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
