/**
 * The look of the city: a warm, hand-made 2.5D style.
 *
 * Plan view stays top-down (so clicks map straight to the city's coordinates), and
 * every building is lifted by its height: the roof is drawn ``z`` units up the
 * screen and a front wall fills the gap, like a paper model seen from the south.
 * Shadows are cast on the ground from the real sun position, so they swing from
 * west to east through the day and stretch long at dawn and dusk.
 *
 * Everything here is pure (no Pixi, no DOM) so it can be tested.
 */

export interface Footprint {
  id: number;
  kind: string;
  x: number;
  y: number;
  w: number;
  h: number;
  households?: number;
  district?: string;
  central?: boolean;
}

export type Pt = [number, number];

/** Paper-and-ink palette. Each kind has a roof colour; walls are the roof darkened. */
export const PALETTE = {
  paper: 0xf3ead8,
  land: 0xe4dcc3,
  grass: 0xc9d6a3,
  grassDark: 0x9fb67a,
  undeveloped: 0xe9e1c8,
  sidewalk: 0xd9cfb6,
  road: 0x6f6a66,
  roadEdge: 0x57524f,
  roadLine: 0xefe2b8,
  ink: 0x3b2f27,
  water: 0x6aa9c9,
  waterDeep: 0x4a8fb3,
  lotusPad: 0x5f9b4c,
  lotusFlower: 0xf2a7b8,
  tree: 0x6f9a52,
  treeDark: 0x557d3e,
  shadow: 0x2b2340,
  window: 0x4a5566,
  windowLit: 0xffd27a,
  night: 0x141a3a,
  lamp: 0xffc766,
} as const;

export const ROOF: Record<string, number> = {
  home: 0xd98c6a, // terracotta tiles
  apartment: 0xc9a37c,
  office: 0x9fb6cc,
  shop: 0xe8b75a,
  restaurant: 0xd46f5c,
  factory: 0xa79e94,
  school: 0xb39ad6,
  hospital: 0xf0f0ec,
  police: 0x7b93c9,
  city_hall: 0xe9cf7f,
  bank: 0x8fbf9f,
  park: 0xc9d6a3,
  bus_depot: 0xb7aea0,
  // places of worship, in the colours of the stone they are usually built from
  temple: 0xe9b872, // sandstone
  mosque: 0xeee6d2,
  church: 0xc98a6b, // brick
  gurudwara: 0xf6f2e6, // white marble
  vihara: 0xf0e6cf,
  derasar: 0xf3eee4, // white marble
  agiary: 0xcdbfa6,
  worship: 0x149c8f, // the compound wall around every place of worship, and the legend swatch
};

/** Places of worship, one legend entry for all of them. */
export const WORSHIP_KINDS = ["temple", "mosque", "church", "gurudwara", "vihara", "derasar", "agiary"];

/** People by what they are doing: saturated enough to read against the paper city. */
export const PEOPLE = [
  0x5b6c9e, // sleeping
  0xa1866a, // at home
  0xe0a03c, // eating at home
  0xe3672f, // eating out
  0x2c7fb8, // working
  0x8a4fc6, // at school
  0xd9467f, // visiting friends
  0x2f9a52, // at the park
  0xc9a10f, // shopping
  0x26201c, // travelling
  0x149c8f, // at a place of worship
];

export const LEGEND_KINDS: [string, string][] = [
  ["home", "Houses"],
  ["apartment", "Apartments"],
  ["office", "Offices"],
  ["shop", "Shops"],
  ["restaurant", "Restaurants"],
  ["factory", "Factories"],
  ["school", "Schools"],
  ["hospital", "Hospital"],
  ["police", "Police"],
  ["city_hall", "City Hall"],
  ["bank", "Bank"],
  ["park", "Parks"],
  ["worship", "Places of worship"],
];

/** A small deterministic hash so every building keeps its height and wobble between reloads. */
export function hash01(n: number, salt = 0): number {
  let h = (n * 374761393 + salt * 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967295;
}

export function styleKind(b: Footprint): string {
  return b.kind === "home" && (b.households ?? 0) > 3 ? "apartment" : b.kind;
}

/** Height in city metres. Offices in the centre are towers; houses are low. */
export function buildingHeight(b: Footprint): number {
  const r = hash01(b.id, 1);
  switch (styleKind(b)) {
    case "home":
      return 9 + 5 * r;
    case "apartment":
      return 26 + 22 * r;
    case "office":
      return (b.central ? 70 : 42) + 45 * r;
    case "shop":
      return 11 + 4 * r;
    case "restaurant":
      return 9 + 4 * r;
    case "factory":
      return 16 + 6 * r;
    case "school":
      return 15 + 3 * r;
    case "hospital":
      return 46 + 8 * r;
    case "police":
      return 22;
    case "city_hall":
      return 32;
    case "bank":
      return 40;
    case "bus_depot":
      return 10;
    case "temple":
    case "derasar":
      return 12 + 3 * r; // the spire rises above this
    case "mosque":
    case "gurudwara":
      return 14 + 3 * r;
    case "church":
      return 16 + 3 * r;
    case "vihara":
    case "agiary":
      return 9 + 2 * r;
    default:
      return 0;
  }
}

/** On screen a metre of height lifts the roof by this many plan units. */
export const LIFT = 0.55;

export function shade(color: number, f: number): number {
  const r = Math.round(((color >> 16) & 255) * f);
  const g = Math.round(((color >> 8) & 255) * f);
  const b = Math.round((color & 255) * f);
  return (Math.min(255, r) << 16) | (Math.min(255, g) << 8) | Math.min(255, b);
}

export function mix(a: number, b: number, t: number): number {
  const ch = (c: number, s: number) => (c >> s) & 255;
  const m = (s: number) => Math.round(ch(a, s) + (ch(b, s) - ch(a, s)) * t);
  return (m(16) << 16) | (m(8) << 8) | m(0);
}

/** Corners of a rectangle with a hand-drawn wobble of up to ``amp`` units. */
export function wobblyRect(x: number, y: number, w: number, h: number, seed: number, amp = 1.2): Pt[] {
  const j = (k: number) => (hash01(seed, k) - 0.5) * 2 * amp;
  return [
    [x + j(1), y + j(2)],
    [x + w + j(3), y + j(4)],
    [x + w + j(5), y + h + j(6)],
    [x + j(7), y + h + j(8)],
  ];
}

/**
 * Where a building's shadow falls. The sun's azimuth is clockwise from north and the
 * map's y axis points south, so the shadow points away from the sun: (-sin az, +cos az).
 * Length is height / tan(elevation), capped so dawn shadows do not cross the city.
 * Returns the convex hull of the footprint and the footprint pushed along the shadow.
 */
export function shadowPolygon(b: Footprint, height: number, sunElevationDeg: number, sunAzimuthDeg: number): Pt[] | null {
  if (sunElevationDeg <= 0.5 || height <= 0) return null;
  const len = Math.min(height / Math.tan((sunElevationDeg * Math.PI) / 180), height * 6);
  const az = (sunAzimuthDeg * Math.PI) / 180;
  const dx = -Math.sin(az) * len;
  const dy = Math.cos(az) * len;
  const base: Pt[] = [
    [b.x, b.y],
    [b.x + b.w, b.y],
    [b.x + b.w, b.y + b.h],
    [b.x, b.y + b.h],
  ];
  return convexHull([...base, ...base.map(([x, y]) => [x + dx, y + dy] as Pt)]);
}

/** Andrew's monotone chain. */
export function convexHull(points: Pt[]): Pt[] {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return pts;
  const cross = (o: Pt, a: Pt, b: Pt) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: Pt[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: Pt[] = [];
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

/** Window rectangles on a front wall: rows per storey, columns across the width. */
export function windowGrid(b: Footprint, height: number): { x: number; y: number; w: number; h: number; key: number }[] {
  const out: { x: number; y: number; w: number; h: number; key: number }[] = [];
  const kind = styleKind(b);
  if (kind === "park" || height < 8) return out;
  const wall = height * LIFT;
  const storey = kind === "office" ? 7 : 6.5;
  const rows = Math.max(1, Math.floor(wall / storey));
  const cols = Math.max(1, Math.floor((b.w - 6) / 9));
  const cw = (b.w - 6) / cols;
  const rh = wall / rows;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      out.push({ x: b.x + 3 + c * cw + cw * 0.25, y: b.y + b.h - wall + r * rh + rh * 0.25, w: cw * 0.5, h: rh * 0.45, key: r * 131 + c });
    }
  }
  return out;
}

/** How much of the sky's light reaches the streets (0 = night, 1 = full day). */
export function daylight(sunElevationDeg: number, cloudPct: number): number {
  const d = Math.min(1, Math.max(0, (sunElevationDeg + 7) / 15));
  return d * (1 - 0.25 * (cloudPct / 100));
}

/** Warm tint at sunrise/sunset, cool at night, none at noon. */
export function skyTint(sunElevationDeg: number): { color: number; alpha: number } {
  if (sunElevationDeg < -6) return { color: PALETTE.night, alpha: 0.55 };
  if (sunElevationDeg < 0) return { color: mix(PALETTE.night, 0x8a4a6a, (sunElevationDeg + 6) / 6), alpha: 0.55 - ((sunElevationDeg + 6) / 6) * 0.3 };
  if (sunElevationDeg < 10) return { color: 0xf0a060, alpha: 0.18 * (1 - sunElevationDeg / 10) };
  return { color: 0xffffff, alpha: 0 };
}
