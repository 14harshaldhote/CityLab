/**
 * Toy-town 3D models for every building, tree, street and lamp in the city.
 *
 * Nothing here touches three.js: each model is a list of simple parts (a box, a
 * gable roof, a pyramid, a cone, a cylinder, a dome, a ball) with a position, a
 * size and a colour. The 3D view turns every kind of part into one instanced mesh,
 * so the whole city draws in a handful of calls, and the lists can be tested here.
 *
 * Axes: x is east, z is south (the city's y), and y is up. Sizes are metres.
 */

import type { Building, CityMap } from "../api/types";
import { buildingHeight, hash01, styleKind } from "./art";

export type Shape = "box" | "roof" | "pyramid" | "cone" | "cyl" | "dome" | "ball";

export interface Part {
  s: Shape;
  x: number; // centre of the base
  y: number; // bottom
  z: number;
  w: number; // size along x, y (height) and z
  h: number;
  d: number;
  ry?: number; // turn about the up axis, radians
  c: number; // colour
  bid: number; // building it belongs to, -1 for streets and trees
  flat?: boolean; // ground pads: receive shadows, cast none
  glow?: boolean; // lamps and fire: lit from inside
}

export interface Win {
  x: number;
  y: number;
  z: number;
  w: number;
  h: number;
  ry: number; // which way the wall faces
  bid: number;
  key: number; // stable per window, decides which rooms have the lights on
}

export interface Model {
  parts: Part[];
  windows: Win[];
}

// colours: sunny Indian pastels, terracotta, sandstone and marble
export const C = {
  land: 0xd9cfa8,
  field: 0xc8c48c,
  pavement: 0xd8cdb6,
  paving: 0xc9bca3,
  lawn: 0x9cc06e,
  grass: 0x8db85f,
  road: 0x5b5754,
  roadLine: 0xf3e3a8,
  zebra: 0xf2efe6,
  water: 0x5aa7cf,
  lotusPad: 0x4f8f3e,
  lotus: 0xf49ab3,
  trunk: 0x7a5636,
  leaf: [0x5f9e48, 0x4f8a3c, 0x78ad4f, 0x6aa04a],
  terracotta: 0xc8613f,
  roofRed: 0xb8483a,
  walls: [0xf2dcae, 0xf4bfa3, 0xa9d8c4, 0xa3c8ea, 0xcdb8e3, 0xf5e38a, 0xf3b0c0, 0xece6da],
  glass: 0x7fa7c9,
  glassDark: 0x56789c,
  concrete: 0xd7d2c8,
  tank: 0x2d2d2d,
  white: 0xf7f4ec,
  marble: 0xf3efe6,
  sandstone: 0xe2b479,
  saffron: 0xf08a24,
  gold: 0xe7b53b,
  green: 0x3f8f5a,
  red: 0xd2463c,
  blue: 0x3f63a5,
  brick: 0xb86b4b,
  slate: 0x6b7f99,
  steel: 0x9aa3ad,
  pole: 0x55585c,
  lamp: 0xffd27a,
  awning: [0xd2463c, 0x3f8f6a, 0xf08a24, 0x3f63a5],
  wood: 0x8c6239,
  dirt: 0xb48d5e,
  sand: 0xe0c48a,
  sheet: 0x3f6fb5,
  crane: 0xf2b32a,
};

const pick = <T,>(xs: readonly T[], id: number, salt: number): T => xs[Math.floor(hash01(id, salt) * xs.length) % xs.length];

/** The 3D model of one building on its lot. */
export function buildingModel(b: Building): Model {
  const parts: Part[] = [];
  const windows: Win[] = [];
  if (b.status === "construction") return siteModel(b);
  const kind = styleKind(b);
  const H = buildingHeight(b);
  const cx = b.x + b.w / 2;
  const cz = b.y + b.h / 2;
  const P = (s: Shape, x: number, y: number, z: number, w: number, h: number, d: number, c: number, more: Partial<Part> = {}) =>
    parts.push({ s, x, y, z, w, h, d, c, bid: b.id, ...more });

  // the lot itself: paving for most buildings, lawn for homes and parks
  const lot = kind === "park" ? C.grass : kind === "home" ? C.lawn : C.paving;
  P("box", cx, 0, cz, b.w, 0.4, b.h, lot, { flat: true });

  /** Windows on all four walls of a box, one row per storey. */
  const glaze = (x: number, z: number, w: number, d: number, y0: number, y1: number, storey = 3.4, every = 4.5) => {
    const rows = Math.max(1, Math.floor((y1 - y0 - 1) / storey));
    const faces: [number, number, number, number][] = [
      // centre x, centre z, wall length, facing (radians)
      [x, z + d / 2 + 0.05, w, 0],
      [x, z - d / 2 - 0.05, w, Math.PI],
      [x + w / 2 + 0.05, z, d, Math.PI / 2],
      [x - w / 2 - 0.05, z, d, -Math.PI / 2],
    ];
    faces.forEach(([fx, fz, len, ry], f) => {
      const cols = Math.max(1, Math.floor((len - 2) / every));
      for (let r = 0; r < rows; r++) {
        for (let k = 0; k < cols; k++) {
          const along = -len / 2 + 1 + (k + 0.5) * ((len - 2) / cols);
          const wx = fx + Math.cos(ry) * along;
          const wz = fz - Math.sin(ry) * along;
          windows.push({ x: wx, y: y0 + 1.2 + r * storey, z: wz, w: Math.min(2.2, (len - 2) / cols - 0.8), h: storey * 0.5, ry, bid: b.id, key: f * 10000 + r * 100 + k });
        }
      }
    });
  };

  switch (kind) {
    case "home": {
      // a few bungalows with tiled roofs, each in its own garden
      const n = Math.min(4, Math.max(2, b.households || 2));
      const cells = n <= 2 ? [[0.25, 0.5], [0.75, 0.5]] : [[0.25, 0.27], [0.75, 0.27], [0.25, 0.75], [0.75, 0.75]].slice(0, n);
      cells.forEach(([u, v], k) => {
        const hx = b.x + u * b.w;
        const hz = b.y + v * b.h;
        const bw = b.w * 0.3;
        const bd = b.h * (n <= 2 ? 0.34 : 0.24);
        const wall = 6 + 3 * hash01(b.id * 7 + k, 2);
        const col = pick(C.walls, b.id * 7 + k, 3);
        P("box", hx, 0, hz, bw, wall, bd, col);
        P("roof", hx, wall, hz, bw + 1.6, 3.5 + 1.5 * hash01(b.id * 7 + k, 4), bd + 1.2, hash01(b.id * 7 + k, 5) < 0.6 ? C.terracotta : C.roofRed);
        P("box", hx, 0, hz + bd / 2 + 0.05, 2, 3.4, 0.2, C.wood); // door
        glaze(hx, hz, bw, bd, 0, wall, 4, 6);
        tree(parts, hx + bw * 0.75, hz - bd * 0.55, 0.8 + 0.4 * hash01(b.id * 7 + k, 6), b.id * 7 + k);
      });
      break;
    }
    case "apartment": {
      // one or two housing-society towers with balconies and black water tanks on the roof
      const two = b.w > 70;
      const tw = two ? b.w * 0.36 : b.w * 0.6;
      const td = b.h * 0.55;
      const col = pick(C.walls, b.id, 3);
      for (const off of two ? [-0.22, 0.22] : [0]) {
        const tx = cx + off * b.w;
        P("box", tx, 0, cz, tw, H, td, col);
        P("box", tx, H, cz, tw + 0.6, 1.2, td + 0.6, C.concrete); // parapet
        for (let y = 3.4; y < H - 1; y += 3.4) P("box", tx, y, cz + td / 2 + 0.7, tw * 0.9, 0.35, 1.4, C.concrete); // balconies
        P("box", tx - tw * 0.25, H, cz - td * 0.2, tw * 0.22, 3, td * 0.25, C.concrete); // stair room
        for (const k of [0, 1, 2]) P("cyl", tx + tw * (0.05 + 0.13 * k), H + 1.2, cz + td * 0.15, 2.6, 2.8, 2.6, C.tank);
        glaze(tx, cz, tw, td, 0, H);
      }
      tree(parts, b.x + b.w * 0.12, b.y + b.h * 0.85, 1, b.id);
      tree(parts, b.x + b.w * 0.88, b.y + b.h * 0.85, 1.1, b.id + 1);
      break;
    }
    case "office": {
      // a glass tower on a stone podium, with a crown
      const tw = b.w * 0.55;
      const td = b.h * 0.55;
      P("box", cx, 0, cz, b.w * 0.8, 6, b.h * 0.8, C.concrete);
      P("box", cx, 6, cz, tw, H - 6, td, hash01(b.id, 3) < 0.5 ? C.glass : C.glassDark);
      P("box", cx, H, cz, tw * 0.7, 4, td * 0.7, C.concrete);
      if (hash01(b.id, 9) < 0.4) P("cyl", cx, H + 4, cz, 0.6, 10, 0.6, C.steel); // antenna
      glaze(cx, cz, tw, td, 6, H, 3.8, 3.2);
      break;
    }
    case "shop": {
      // a row of shop fronts with striped awnings along the street side
      const units = 4;
      const uw = (b.w * 0.92) / units;
      const depth = b.h * 0.42;
      const z0 = b.y + b.h - depth / 2 - 3;
      for (let k = 0; k < units; k++) {
        const ux = b.x + b.w * 0.04 + uw * (k + 0.5);
        const wall = 8 + 3 * hash01(b.id * 5 + k, 2);
        P("box", ux, 0, z0, uw - 0.6, wall, depth, pick(C.walls, b.id * 5 + k, 3));
        P("box", ux, wall - 3.6, z0 + depth / 2 + 1.4, uw - 1.2, 0.4, 2.8, pick(C.awning, b.id * 5 + k, 4), { ry: 0 });
        P("box", ux, wall, z0, uw - 0.6, 1.6, depth, C.concrete); // signboard band
        windows.push({ x: ux, y: 1, z: z0 + depth / 2 + 0.05, w: uw * 0.6, h: 3, ry: 0, bid: b.id, key: k });
      }
      P("box", cx, 0, b.y + b.h * 0.25, b.w * 0.8, 0.45, b.h * 0.3, C.pavement, { flat: true }); // parking
      break;
    }
    case "restaurant": {
      const bw = b.w * 0.62;
      const bd = b.h * 0.48;
      const bz = b.y + b.h * 0.38;
      P("box", cx, 0, bz, bw, H, bd, pick(C.walls, b.id, 3));
      P("roof", cx, H, bz, bw + 2, 4, bd + 2, C.roofRed);
      P("box", cx, H - 3.2, bz + bd / 2 + 1.6, bw, 0.4, 3.2, pick(C.awning, b.id, 4));
      glaze(cx, bz, bw, bd, 0, H, 4, 5);
      // tables with umbrellas out front
      for (let k = 0; k < 4; k++) {
        const ux = b.x + b.w * (0.2 + 0.2 * k);
        const uz = b.y + b.h * 0.82;
        P("cyl", ux, 0, uz, 0.4, 3.2, 0.4, C.pole);
        P("cone", ux, 3, uz, 6, 1.6, 6, pick(C.awning, b.id + k, 6));
      }
      break;
    }
    case "factory": {
      // a long shed with a saw-tooth roof, a chimney and a storage tank
      const bw = b.w * 0.88;
      const bd = b.h * 0.7;
      const wall = 11;
      P("box", cx, 0, cz, bw, wall, bd, C.concrete);
      const teeth = 5;
      for (let k = 0; k < teeth; k++) {
        P("roof", b.x + b.w * 0.06 + (bw / teeth) * (k + 0.5), wall, cz, bw / teeth, 5, bd, C.steel);
      }
      P("cyl", b.x + b.w * 0.85, 0, b.y + b.h * 0.2, 4, 34, 4, C.brick);
      P("cyl", b.x + b.w * 0.85, 34, b.y + b.h * 0.2, 4.4, 2, 4.4, C.red);
      P("cyl", b.x + b.w * 0.15, 0, b.y + b.h * 0.12, 9, 10, 9, C.white);
      break;
    }
    case "school": {
      // an L-shaped school around a playground, with the flag
      const col = 0xf2d38a;
      P("box", cx, 0, b.y + b.h * 0.22, b.w * 0.85, H, b.h * 0.26, col);
      P("box", b.x + b.w * 0.14, 0, cz + b.h * 0.1, b.w * 0.18, H, b.h * 0.55, col);
      P("box", cx + b.w * 0.1, 0, cz + b.h * 0.18, b.w * 0.55, 0.45, b.h * 0.4, 0xd9b98c, { flat: true }); // playground
      glaze(cx, b.y + b.h * 0.22, b.w * 0.85, b.h * 0.26, 0, H, 4, 5);
      flag(parts, b.x + b.w * 0.88, b.y + b.h * 0.5, 16, C.saffron, b.id);
      break;
    }
    case "hospital": {
      P("box", cx, 0, cz, b.w * 0.75, H, b.h * 0.55, C.white);
      P("box", cx, 0, cz + b.h * 0.33, b.w * 0.4, 6, b.h * 0.12, C.concrete); // entrance canopy
      P("box", cx, H, cz, 4, 0.5, 14, C.red);
      P("box", cx, H, cz, 14, 0.5, 4, C.red);
      glaze(cx, cz, b.w * 0.75, b.h * 0.55, 0, H);
      break;
    }
    case "police": {
      P("box", cx, 0, cz, b.w * 0.7, H, b.h * 0.55, 0xe7ecf3);
      P("box", cx, H - 4, cz, b.w * 0.72, 4, b.h * 0.57, C.blue);
      P("ball", cx, H, cz, 3, 3, 3, C.red, { glow: true });
      glaze(cx, cz, b.w * 0.7, b.h * 0.55, 0, H - 4);
      flag(parts, b.x + b.w * 0.88, b.y + b.h * 0.85, 14, C.saffron, b.id);
      break;
    }
    case "city_hall": {
      // the municipal corporation: a cream hall with columns and a dome
      const bw = b.w * 0.75;
      const bd = b.h * 0.55;
      P("box", cx, 0, cz, bw + 6, 2, bd + 8, C.concrete);
      P("box", cx, 2, cz, bw, H - 2, bd, 0xf1e2b8);
      for (let k = 0; k < 8; k++) P("cyl", cx - bw * 0.42 + k * (bw * 0.84) / 7, 2, cz + bd / 2 + 2, 1.6, H - 6, 1.6, C.white);
      P("box", cx, H - 4, cz + bd / 2 + 2, bw * 0.9, 2, 4, C.white);
      P("cyl", cx, H, cz, 18, 6, 18, 0xf1e2b8);
      P("dome", cx, H + 6, cz, 18, 10, 18, C.gold);
      flag(parts, cx, cz, H + 26, C.saffron, b.id, 0);
      glaze(cx, cz, bw, bd, 2, H - 4);
      break;
    }
    case "bank": {
      const bw = b.w * 0.7;
      const bd = b.h * 0.5;
      P("box", cx, 0, cz, bw, H, bd, 0xdfe9df);
      for (let k = 0; k < 6; k++) P("cyl", cx - bw * 0.4 + k * (bw * 0.8) / 5, 0, cz + bd / 2 + 2.5, 1.8, H * 0.6, 1.8, C.white);
      P("roof", cx, H * 0.6, cz + bd / 2 + 2.5, bw * 0.9, 5, 5, C.white);
      glaze(cx, cz, bw, bd, 0, H);
      break;
    }
    case "bus_depot": {
      P("box", cx, 9, cz, b.w * 0.8, 1, b.h * 0.6, C.steel);
      for (let k = 0; k < 4; k++) for (const s of [-1, 1]) P("cyl", cx - b.w * 0.35 + k * b.w * 0.233, 0, cz + s * b.h * 0.27, 1, 9, 1, C.pole);
      for (let k = 0; k < 4; k++) P("box", cx - b.w * 0.27 + k * b.w * 0.18, 0, cz, 5, 4.5, 16, k % 2 ? C.red : 0x3f8f6a);
      break;
    }
    case "park": {
      const central = b.name === "Kamal Talav";
      const pond = central || hash01(b.id, 3) < 0.5;
      if (pond) {
        const rx = b.w * (central ? 0.6 : 0.45);
        const rz = b.h * (central ? 0.42 : 0.32);
        P("cyl", cx, 0, cz, rx + 4, 0.5, rz + 4, 0xb9c99a, { flat: true });
        P("cyl", cx, 0, cz, rx, 0.65, rz, C.water, { flat: true });
        for (let k = 0; k < (central ? 26 : 10); k++) {
          const a = hash01(b.id * 31 + k, 4) * Math.PI * 2;
          const rr = 0.2 + 0.7 * hash01(b.id * 31 + k, 5);
          const lx = cx + (Math.cos(a) * rx * rr) / 2;
          const lz = cz + (Math.sin(a) * rz * rr) / 2;
          P("cyl", lx, 0.65, lz, 3.4, 0.15, 3.4, C.lotusPad, { flat: true });
          if (k % 3 === 0) P("cone", lx, 0.8, lz, 1.6, 1.4, 1.6, C.lotus);
        }
      }
      const trees = Math.round((b.w * b.h) / 900);
      for (let k = 0; k < trees; k++) {
        const tx = b.x + 6 + hash01(b.id * 97 + k, 6) * (b.w - 12);
        const tz = b.y + 6 + hash01(b.id * 97 + k, 7) * (b.h - 12);
        if (pond && ((tx - cx) / (b.w * (central ? 0.36 : 0.28))) ** 2 + ((tz - cz) / (b.h * (central ? 0.26 : 0.21))) ** 2 < 1) continue;
        tree(parts, tx, tz, 0.9 + 0.6 * hash01(b.id * 97 + k, 8), b.id * 97 + k);
      }
      // two benches and a path
      P("box", cx, 0, b.y + b.h - 8, b.w * 0.9, 0.5, 4, C.pavement, { flat: true });
      for (const s of [-1, 1]) P("box", cx + s * b.w * 0.2, 0, b.y + b.h - 13, 6, 1.6, 1.6, C.wood);
      break;
    }
    case "temple": {
      // a Hindu mandir: a stone plinth, the hall (mandapa) and a tall spire (shikhara) with a saffron flag
      const s = Math.min(b.w, b.h);
      P("box", cx, 0, cz, s * 0.62, 2.5, s * 0.72, C.sandstone);
      P("box", cx, 2.5, cz + s * 0.12, s * 0.42, 7, s * 0.3, C.sandstone);
      P("pyramid", cx, 9.5, cz + s * 0.12, s * 0.46, 6, s * 0.34, 0xd9a463);
      P("box", cx, 2.5, cz - s * 0.14, s * 0.3, 8, s * 0.26, C.sandstone);
      shikhara(parts, cx, 10.5, cz - s * 0.14, s * 0.3, 26, 0xe8bd85, C.saffron, b.id);
      break;
    }
    case "derasar": {
      // a Jain derasar in white marble, three spires with red flags
      const s = Math.min(b.w, b.h);
      P("box", cx, 0, cz, s * 0.7, 3, s * 0.7, C.marble);
      P("box", cx, 3, cz, s * 0.5, 8, s * 0.42, C.marble);
      shikhara(parts, cx, 11, cz - s * 0.04, s * 0.26, 22, C.marble, C.red, b.id);
      for (const dx of [-1, 1]) shikhara(parts, cx + dx * s * 0.2, 11, cz + s * 0.1, s * 0.14, 12, C.marble, C.red, b.id);
      break;
    }
    case "mosque": {
      // a masjid: a white prayer hall, a green dome and two slender minarets
      const s = Math.min(b.w, b.h);
      P("box", cx, 0, cz, s * 0.75, 0.6, s * 0.75, C.marble, { flat: true }); // courtyard
      P("box", cx, 0, cz - s * 0.1, s * 0.55, 10, s * 0.38, C.white);
      P("cyl", cx, 10, cz - s * 0.1, s * 0.26, 3, s * 0.26, C.white);
      P("dome", cx, 13, cz - s * 0.1, s * 0.26, s * 0.2, s * 0.26, 0x5e9b6f);
      P("cone", cx, 13 + s * 0.2, cz - s * 0.1, 1, 3, 1, C.gold);
      for (const dx of [-1, 1]) {
        const mx = cx + dx * s * 0.33;
        const mz = cz + s * 0.1;
        P("cyl", mx, 0, mz, 3.2, 30, 3.2, C.white);
        P("cyl", mx, 22, mz, 4.6, 1, 4.6, C.concrete);
        P("dome", mx, 30, mz, 3.6, 3, 3.6, 0x5e9b6f);
      }
      break;
    }
    case "church": {
      // a brick church with a long gabled nave and a bell tower with a spire and a cross
      const s = Math.min(b.w, b.h);
      P("box", cx, 0, cz - s * 0.05, s * 0.3, 11, s * 0.55, C.brick);
      P("roof", cx, 11, cz - s * 0.05, s * 0.34, 8, s * 0.56, C.slate);
      const tz = cz + s * 0.26;
      P("box", cx, 0, tz, 9, 22, 9, C.brick);
      P("pyramid", cx, 22, tz, 10, 14, 10, C.slate);
      P("box", cx, 36, tz, 0.8, 6, 0.8, C.white);
      P("box", cx, 39.5, tz, 3.6, 0.8, 0.8, C.white);
      windows.push({ x: cx, y: 13, z: tz + 4.6, w: 2.4, h: 4, ry: 0, bid: b.id, key: 1 });
      break;
    }
    case "gurudwara": {
      // a white gurudwara with a golden dome, small corner domes and the Nishan Sahib on its tall pole
      const s = Math.min(b.w, b.h);
      P("box", cx, 0, cz, s * 0.75, 0.6, s * 0.75, C.marble, { flat: true });
      P("box", cx, 0, cz, s * 0.48, 11, s * 0.42, C.white);
      P("cyl", cx, 11, cz, s * 0.24, 3, s * 0.24, C.white);
      P("dome", cx, 14, cz, s * 0.26, s * 0.18, s * 0.26, C.gold);
      P("cone", cx, 14 + s * 0.18, cz, 1.4, 4, 1.4, C.gold);
      for (const [dx, dz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) {
        P("cyl", cx + dx * s * 0.22, 11, cz + dz * s * 0.19, 3, 2.5, 3, C.white);
        P("dome", cx + dx * s * 0.22, 13.5, cz + dz * s * 0.19, 3.4, 2.6, 3.4, C.gold);
      }
      flag(parts, cx + s * 0.32, cz + s * 0.3, 32, C.saffron, b.id, 0, true);
      break;
    }
    case "vihara": {
      // a Buddha vihar: a hall beside a white stupa with a golden spire
      const s = Math.min(b.w, b.h);
      P("box", cx - s * 0.18, 0, cz, s * 0.26, 8, s * 0.4, C.white);
      P("roof", cx - s * 0.18, 8, cz, s * 0.3, 4, s * 0.42, 0xd2a14a);
      P("cyl", cx + s * 0.16, 0, cz, s * 0.34, 3, s * 0.34, C.concrete);
      P("dome", cx + s * 0.16, 3, cz, s * 0.3, s * 0.17, s * 0.3, C.white);
      P("box", cx + s * 0.16, 3 + s * 0.17, cz, 3.4, 2, 3.4, C.concrete);
      P("cone", cx + s * 0.16, 5 + s * 0.17, cz, 2.2, 8, 2.2, C.gold);
      break;
    }
    case "agiary": {
      // a Parsi agiary: a quiet stone hall with a columned porch, its sacred fire glowing inside
      const s = Math.min(b.w, b.h);
      P("box", cx, 0, cz - s * 0.05, s * 0.45, H, s * 0.36, 0xd8ccb2);
      P("box", cx, H, cz - s * 0.05, s * 0.48, 1.4, s * 0.39, C.concrete);
      for (let k = 0; k < 4; k++) P("cyl", cx - s * 0.15 + k * s * 0.1, 0, cz + s * 0.17, 1.4, H, 1.4, C.white);
      P("ball", cx, 1, cz + s * 0.3, 2.2, 2.2, 2.2, C.saffron, { glow: true });
      break;
    }
    default:
      P("box", cx, 0, cz, b.w * 0.7, Math.max(4, H), b.h * 0.6, C.concrete);
  }
  return { parts, windows };
}

/** How tall a building site will be once finished. */
export function siteHeight(b: Building): number {
  return buildingHeight({ ...b, households: b.planned ?? b.households });
}

/**
 * A building site: tin-sheet fencing, a foundation, sand and bricks, and a tower crane
 * taller than the finished building. The rising structure itself is drawn by the 3D
 * view from each day's progress.
 */
export function siteModel(b: Building): Model {
  const parts: Part[] = [];
  const cx = b.x + b.w / 2;
  const cz = b.y + b.h / 2;
  const P = (s: Shape, x: number, y: number, z: number, w: number, h: number, d: number, c: number, more: Partial<Part> = {}) =>
    parts.push({ s, x, y, z, w, h, d, c, bid: b.id, ...more });
  P("box", cx, 0, cz, b.w, 0.45, b.h, C.dirt, { flat: true });
  P("box", cx, 0.4, cz, b.w * 0.66, 1, b.h * 0.6, C.concrete); // foundation
  // fencing on three sides, with a gate gap at the front
  P("box", cx, 0, b.y + 1, b.w - 2, 2.6, 0.3, C.sheet);
  P("box", b.x + 1, 0, cz, 0.3, 2.6, b.h - 2, C.sheet);
  P("box", b.x + b.w - 1, 0, cz, 0.3, 2.6, b.h - 2, C.sheet);
  P("box", b.x + b.w * 0.25, 0, b.y + b.h - 1, b.w * 0.45, 2.6, 0.3, C.sheet);
  P("box", b.x + b.w * 0.85, 0, b.y + b.h - 1, b.w * 0.3, 2.6, 0.3, C.sheet);
  P("cone", b.x + b.w * 0.18, 0, b.y + b.h * 0.82, 10, 4, 10, C.sand);
  P("box", b.x + b.w * 0.82, 0, b.y + b.h * 0.18, 6, 2.4, 4, C.brick);
  // the tower crane
  const H = siteHeight(b) + 16;
  const tx = b.x + b.w * 0.15;
  const tz = b.y + b.h * 0.2;
  P("box", tx, 0, tz, 2.2, H, 2.2, C.crane);
  P("box", tx, H, tz, 3, 2.6, 3, C.crane); // cab
  const jib = b.w * 0.85;
  P("box", tx + jib / 2 - 2, H + 2.6, tz, jib, 1.2, 1.4, C.crane);
  P("box", tx - 7, H + 2.6, tz, 12, 1.2, 1.4, C.crane);
  P("box", tx - 11, H + 1, tz, 4, 2.6, 2.6, C.concrete); // counterweight
  P("cyl", tx + jib * 0.6, H * 0.45, tz, 0.15, H * 0.55 + 2.6, 0.15, C.pole); // hook line
  P("box", tx + jib * 0.6, H * 0.45 - 1, tz, 2.4, 1, 2.4, C.wood); // load
  return { parts, windows: [] };
}

/** Zoned empty plots: a light pad in the zone's colour, corner stakes and a signboard. */
export function plotModel(city: CityMap): Part[] {
  const parts: Part[] = [];
  const tint = { residential: 0xcfe6a8, commercial: 0xb4d0ec, industrial: 0xd3cabb } as const;
  (city.plots ?? []).forEach((p, k) => {
    const cx = p.x + p.w / 2;
    const cz = p.y + p.h / 2;
    parts.push({ s: "box", x: cx, y: 0, z: cz, w: p.w, h: 0.35, d: p.h, c: tint[p.zone] ?? 0xddd5c0, bid: -1, flat: true });
    for (const [dx, dz] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
      parts.push({ s: "cyl", x: p.x + dx * p.w, y: 0, z: p.y + dz * p.h, w: 0.6, h: 2.2, d: 0.6, c: C.saffron, bid: -1 });
    }
    parts.push({ s: "cyl", x: cx - 3, y: 0, z: p.y + p.h - 4, w: 0.4, h: 4, d: 0.4, c: C.pole, bid: -1 });
    parts.push({ s: "cyl", x: cx + 3, y: 0, z: p.y + p.h - 4, w: 0.4, h: 4, d: 0.4, c: C.pole, bid: -1 });
    parts.push({ s: "box", x: cx, y: 2.6, z: p.y + p.h - 4, w: 8, h: 2.6, d: 0.3, c: k % 2 ? C.white : 0xfff3c4, bid: -1 });
  });
  // streets being laid: dirt roads lined with orange cones
  for (const r of city.roadworks ?? []) {
    const sides: [number, number, number, number, number][] = [
      [r.x + r.w / 2, r.y, r.w, 20, 0],
      [r.x + r.w / 2, r.y + r.h, r.w, 20, 0],
      [r.x, r.y + r.h / 2, r.h, 20, Math.PI / 2],
      [r.x + r.w, r.y + r.h / 2, r.h, 20, Math.PI / 2],
    ];
    for (const [x, z, len, wd, ry] of sides) {
      parts.push({ s: "box", x, y: 0, z, w: len, h: 0.42, d: wd, ry, c: C.dirt, bid: -1, flat: true });
      for (let d = -len / 2 + 10; d < len / 2; d += 26) {
        const ox = Math.cos(ry) * d;
        const oz = -Math.sin(ry) * d;
        parts.push({ s: "cone", x: x + ox, y: 0.4, z: z + oz, w: 1.2, h: 1.8, d: 1.2, c: C.saffron, bid: -1 });
      }
    }
  }
  return parts;
}

function tree(parts: Part[], x: number, z: number, size: number, seed: number) {
  const h = 5 * size;
  parts.push({ s: "cyl", x, y: 0, z, w: 0.9 * size, h, d: 0.9 * size, c: C.trunk, bid: -1 });
  parts.push({ s: "ball", x, y: h - 1.5 * size, z, w: 7 * size, h: 6.5 * size, d: 7 * size, c: pick(C.leaf, seed, 9), bid: -1 });
}

function flag(parts: Part[], x: number, z: number, height: number, color: number, bid: number, y0 = 0, big = false) {
  parts.push({ s: "cyl", x, y: y0, z, w: 0.5, h: height, d: 0.5, c: C.pole, bid });
  const fw = big ? 7 : 4.5;
  parts.push({ s: "box", x: x + fw / 2, y: y0 + height - (big ? 5 : 3.2), z, w: fw, h: big ? 4.4 : 3, d: 0.2, c: color, bid });
}

/** A temple spire: a tall stepped pyramid with a round kalash on top and a flag. */
function shikhara(parts: Part[], x: number, y: number, z: number, base: number, height: number, color: number, flagColor: number, bid: number) {
  parts.push({ s: "pyramid", x, y, z, w: base, h: height, d: base, c: color, bid });
  for (let k = 1; k < 4; k++) {
    const t = k / 4;
    parts.push({ s: "box", x, y: y + height * t * 0.85, z, w: base * (1 - t) * 0.92, h: 0.8, d: base * (1 - t) * 0.92, c: color, bid });
  }
  parts.push({ s: "ball", x, y: y + height - 0.5, z, w: base * 0.14, h: base * 0.14, d: base * 0.14, c: C.gold, bid });
  flag(parts, x, z, 6, flagColor, bid, y + height);
}

/** Streets, crossings, pavements, street lamps and the trees along the avenues. */
export function streetModel(city: CityMap): { parts: Part[]; lamps: { x: number; z: number }[] } {
  const parts: Part[] = [];
  const lamps: { x: number; z: number }[] = [];
  const byId = new Map(city.nodes.map((n) => [n.id, n]));
  const sp = city.spacing;
  // a pavement under every block that has buildings
  const blocks = new Set<string>();
  for (const b of city.buildings) blocks.add(`${Math.floor(b.x / sp)},${Math.floor(b.y / sp)}`);
  for (const key of blocks) {
    const [i, j] = key.split(",").map(Number);
    parts.push({ s: "box", x: (i + 0.5) * sp, y: 0, z: (j + 0.5) * sp, w: sp - 20, h: 0.3, d: sp - 20, c: C.pavement, bid: -1, flat: true });
  }
  city.edges.forEach(([a, b], k) => {
    const na = byId.get(a)!;
    const nb = byId.get(b)!;
    const len = Math.hypot(nb.x - na.x, nb.y - na.y);
    const ry = Math.atan2(-(nb.y - na.y), nb.x - na.x); // along the street
    const mx = (na.x + nb.x) / 2;
    const mz = (na.y + nb.y) / 2;
    parts.push({ s: "box", x: mx, y: 0, z: mz, w: len, h: 0.36, d: 20, ry, c: C.road, bid: -1, flat: true });
    const ux = (nb.x - na.x) / len;
    const uz = (nb.y - na.y) / len;
    for (let d = 22; d < len - 22; d += 20) {
      parts.push({ s: "box", x: na.x + ux * d, y: 0.36, z: na.y + uz * d, w: 8, h: 0.05, d: 0.7, ry, c: C.roadLine, bid: -1, flat: true });
    }
    // a zebra crossing at the start of every street
    for (let s = -4; s <= 4; s++) {
      parts.push({ s: "box", x: na.x + ux * 15 + -uz * s * 2, y: 0.36, z: na.y + uz * 15 + ux * s * 2, w: 4, h: 0.05, d: 1, ry, c: C.zebra, bid: -1, flat: true });
    }
    // avenue trees on every third street
    if (k % 3 === 0) {
      for (let d = 40; d < len - 40; d += 45) {
        tree(parts, na.x + ux * d - uz * 14, na.y + uz * d + ux * 14, 0.7, k * 13 + d);
      }
    }
  });
  for (const n of city.nodes) {
    parts.push({ s: "box", x: n.x, y: 0, z: n.y, w: 20, h: 0.37, d: 20, c: C.road, bid: -1, flat: true });
    const lx = n.x + 13;
    const lz = n.y + 13;
    parts.push({ s: "cyl", x: lx, y: 0, z: lz, w: 0.6, h: 9, d: 0.6, c: C.pole, bid: -1 });
    parts.push({ s: "ball", x: lx, y: 8.6, z: lz, w: 1.8, h: 1.8, d: 1.8, c: C.lamp, bid: -1, glow: true });
    lamps.push({ x: lx, z: lz });
  }
  return { parts, lamps };
}

/** Farmland and scrub on the empty land around the city: room to grow into. */
export function outskirtsModel(city: CityMap, ring = 3): Part[] {
  const parts: Part[] = [];
  const sp = city.spacing;
  const used = new Set<string>();
  for (const b of city.buildings) used.add(`${Math.floor(b.x / sp)},${Math.floor(b.y / sp)}`);
  const n = Math.round(city.size / sp);
  const crops = [0xb7c46a, 0xa3bd5f, 0xd8c873, 0x8fb35a, 0xc9b26a];
  for (let i = -ring; i < n + ring; i++) {
    for (let j = -ring; j < n + ring; j++) {
      if (used.has(`${i},${j}`)) continue;
      const id = (i + 50) * 1000 + j + 50;
      // two or three fields per block, separated by bunds
      const split = hash01(id, 1) < 0.5;
      const k = 2 + Math.floor(hash01(id, 2) * 2);
      for (let f = 0; f < k; f++) {
        const w = split ? (sp - 16) / k : sp - 16;
        const d = split ? sp - 16 : (sp - 16) / k;
        const x = i * sp + 8 + (split ? w * (f + 0.5) : w / 2);
        const z = j * sp + 8 + (split ? d / 2 : d * (f + 0.5));
        parts.push({ s: "box", x, y: 0, z, w: w - 3, h: 0.2, d: d - 3, c: pick(crops, id * 7 + f, 3), bid: -1, flat: true });
      }
      if (hash01(id, 4) < 0.35) tree(parts, i * sp + 10 + hash01(id, 5) * (sp - 20), j * sp + 10 + hash01(id, 6) * (sp - 20), 1.2, id);
    }
  }
  return parts;
}
