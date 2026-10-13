import { Application, Container, Graphics, Texture, TilingSprite } from "pixi.js";
import { useEffect, useRef } from "react";
import type { Building, CityMap as City, Frame } from "../api/types";
import {
  LIFT, PALETTE, PEOPLE, ROOF, WORSHIP_KINDS, buildingHeight, daylight, hash01, shade, shadowPolygon, skyTint, styleKind, windowGrid, wobblyRect,
  type Pt,
} from "../engine/art";
import { lerpFrames, nearestPoint, rectAt } from "../engine/view";

interface Props {
  city: City;
  frames: React.MutableRefObject<{ prev: Frame | null; next: Frame | null; at: number }>;
  selectedPerson: number | null;
  selectedBuilding: number | null;
  onPickPerson: (id: number) => void;
  onPickBuilding: (id: number) => void;
}

const TICK_MS = 200;
const FAR = 20000;
const SLEEPING = 0;

const flat = (pts: Pt[]) => pts.flat();

/**
 * The living map, drawn with PixiJS (WebGL) in a hand-made 2.5D style.
 *
 * Layers, back to front: paper ground and streets, sun shadows (recomputed as the sun
 * moves), buildings lifted by their height and drawn back to front, the sky tint for
 * dawn, dusk and night, lit windows and street lamps (added light), people, the
 * selection marks, and a faint paper grain over everything.
 */
export default function CityMap({ city, frames, selectedPerson, selectedBuilding, onPickPerson, onPickBuilding }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const sel = useRef({ person: selectedPerson, building: selectedBuilding });
  sel.current = { person: selectedPerson, building: selectedBuilding };
  const picks = useRef({ onPickPerson, onPickBuilding });
  picks.current = { onPickPerson, onPickBuilding };

  useEffect(() => {
    const el = host.current!;
    const app = new Application();
    let disposed = false;
    let ready = false;

    const world = new Container();
    const ground = new Graphics();
    const shadows = new Graphics();
    const buildings = new Graphics();
    const tint = new Graphics();
    const lit = new Container();
    const lamps = new Graphics();
    const people = new Graphics();
    const marks = new Graphics();
    world.addChild(ground, shadows, buildings, tint, lit, lamps, people, marks);
    lamps.blendMode = "add";
    lit.blendMode = "add";

    const heights = new Map<number, number>();
    for (const b of city.buildings) heights.set(b.id, buildingHeight(b));
    const lift = (id: number) => (heights.get(id) ?? 0) * LIFT;
    const pos = { x: new Float32Array(0), y: new Float32Array(0) };
    let shownIds: number[] = [];

    drawGround(ground, city);
    const order = [...city.buildings].sort((a, b) => a.y + a.h - (b.y + b.h) || a.x - b.x);
    const litBy = new Map<number, Graphics>();
    for (const b of order) {
      drawBuilding(buildings, b, heights.get(b.id) ?? 0);
      if (b.kind !== "park") {
        const g = new Graphics();
        drawLitWindows(g, b, heights.get(b.id) ?? 0);
        g.alpha = 0;
        lit.addChild(g);
        litBy.set(b.id, g);
      }
    }
    for (const n of city.nodes) {
      lamps.circle(n.x, n.y, 16).fill({ color: PALETTE.lamp, alpha: 0.18 });
      lamps.circle(n.x, n.y, 5).fill({ color: PALETTE.lamp, alpha: 0.6 });
    }

    // ---- camera ----------------------------------------------------------------------------
    const pad = 160;
    const fit = () => {
      const s = Math.min(el.clientWidth / (city.size + 2 * pad), el.clientHeight / (city.size + 2 * pad));
      world.scale.set(s);
      world.position.set((el.clientWidth - city.size * s) / 2, (el.clientHeight - city.size * s) / 2 + 20 * s);
    };
    let drag: { x: number; y: number; moved: boolean } | null = null;
    const toWorld = (cx: number, cy: number) => {
      const r = el.getBoundingClientRect();
      return { x: (cx - r.left - world.x) / world.scale.x, y: (cy - r.top - world.y) / world.scale.y };
    };
    const onDown = (e: PointerEvent) => {
      drag = { x: e.clientX, y: e.clientY, moved: false };
    };
    const onMove = (e: PointerEvent) => {
      if (!drag) return;
      const dx = e.clientX - drag.x;
      const dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      world.x += dx;
      world.y += dy;
      drag.x = e.clientX;
      drag.y = e.clientY;
    };
    let drawnY = new Float32Array(4096);
    const onUp = (e: PointerEvent) => {
      if (drag && !drag.moved) {
        const p = toWorld(e.clientX, e.clientY);
        const i = nearestPoint(pos.x, drawnY.subarray(0, pos.x.length), p.x, p.y, 9 / world.scale.x);
        if (i >= 0 && i < shownIds.length) picks.current.onPickPerson(shownIds[i]);
        else {
          // a click on a roof belongs to the building under it, so test lifted roofs front to back
          const hit = [...order].reverse().find((b) => rectAt([{ x: b.x, y: b.y - lift(b.id), w: b.w, h: b.h + lift(b.id) }], p.x, p.y));
          if (hit) picks.current.onPickBuilding(hit.id);
        }
      }
      drag = null;
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const before = toWorld(e.clientX, e.clientY);
      const s = Math.min(8, Math.max(0.05, world.scale.x * Math.exp(-e.deltaY * 0.0015)));
      world.scale.set(s);
      const r = el.getBoundingClientRect();
      world.x = e.clientX - r.left - before.x * s;
      world.y = e.clientY - r.top - before.y * s;
    };

    // ---- per frame ---------------------------------------------------------------------------
    let sunKey = "";
    const awake = new Map<number, number>();
    const draw = () => {
      const { prev, next, at } = frames.current;
      if (!next) return;
      const n = next.ids.length;
      if (pos.x.length !== n) {
        pos.x = new Float32Array(n);
        pos.y = new Float32Array(n);
      }
      if (drawnY.length < n) drawnY = new Float32Array(n * 2);
      const f = Math.min(1, (performance.now() - at) / TICK_MS);
      lerpFrames(prev ?? next, next, prev ? f : 1, pos);
      shownIds = next.ids;

      const w = next.weather;
      const az = w.sun_azimuth_deg ?? 180;
      const key = `${w.sun_elevation_deg.toFixed(1)}:${az.toFixed(0)}`;
      if (key !== sunKey) {
        sunKey = key;
        shadows.clear();
        const strength = Math.min(1, Math.max(0, w.sun_elevation_deg / 8)) * (1 - 0.6 * (w.cloud_pct / 100));
        if (strength > 0.02) {
          for (const b of city.buildings) {
            const poly = shadowPolygon(b, heights.get(b.id) ?? 0, w.sun_elevation_deg, az);
            if (poly) shadows.poly(flat(poly)).fill({ color: PALETTE.shadow, alpha: 0.2 * strength });
          }
        }
        const t = skyTint(w.sun_elevation_deg);
        tint.clear();
        if (t.alpha > 0.005) tint.rect(-FAR, -FAR, 2 * FAR, 2 * FAR).fill({ color: t.color, alpha: t.alpha });
      }
      const night = 1 - daylight(w.sun_elevation_deg, w.cloud_pct);
      lamps.alpha = Math.max(0, night - 0.3) * 1.4;

      // windows glow where people are home and awake (or at work, school, a meal)
      awake.clear();
      for (let i = 0; i < n; i++) {
        const pl = next.place?.[i] ?? -1;
        if (pl >= 0 && next.activity[i] !== SLEEPING) awake.set(pl, (awake.get(pl) ?? 0) + 1);
      }
      for (const [bid, g] of litBy) g.alpha = night > 0.25 ? Math.min(1, (awake.get(bid) ?? 0) / 3) * night : 0;

      people.clear();
      const r = Math.max(3.4, 2.4 / world.scale.x);
      const outline = world.scale.x >= 1.1;
      for (let i = 0; i < n; i++) {
        const pl = next.place?.[i] ?? -1;
        const z = pl >= 0 ? lift(pl) : 0;
        const x = pos.x[i];
        const y = pos.y[i] - z;
        drawnY[i] = y;
        const size = next.age[i] < 18 ? r * 0.75 : r;
        if (pl < 0) people.ellipse(x + 1.5, pos.y[i] + 2, size * 1.1, size * 0.5).fill({ color: PALETTE.shadow, alpha: 0.25 });
        people.circle(x, y, size).fill(PEOPLE[next.activity[i]] ?? 0);
        // a paper-white rim only when zoomed in; zoomed out it would speckle the whole map
        if (outline) people.stroke({ width: 0.7 / world.scale.x, color: 0xfffaf0, alpha: 0.8 });
      }

      marks.clear();
      const { person, building } = sel.current;
      if (building !== null) {
        const b = city.buildings[building];
        if (b) {
          const z = lift(b.id);
          marks.rect(b.x - 5, b.y - z - 5, b.w + 10, b.h + z + 10).stroke({ width: 3 / world.scale.x + 1.5, color: 0xd9480f });
        }
      }
      if (person !== null) {
        const i = next.ids.indexOf(person);
        if (i >= 0) marks.circle(pos.x[i], drawnY[i], r * 3.2).stroke({ width: 3 / world.scale.x + 1, color: 0xd9480f });
      }
    };

    (async () => {
      await app.init({ resizeTo: el, background: PALETTE.paper, antialias: true, autoDensity: true, resolution: window.devicePixelRatio || 1 });
      if (disposed) {
        app.destroy(true);
        return;
      }
      ready = true;
      el.appendChild(app.canvas);
      app.stage.addChild(world);
      const grain = new TilingSprite({ texture: paperGrain(), width: 4000, height: 3000 });
      grain.alpha = 0.07;
      grain.eventMode = "none";
      app.stage.addChild(grain);
      fit();
      app.ticker.add(draw);
      app.canvas.addEventListener("pointerdown", onDown);
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      app.canvas.addEventListener("wheel", onWheel, { passive: false });
      app.canvas.addEventListener("dblclick", fit);
    })();

    return () => {
      disposed = true;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (ready) app.destroy(true, { children: true });
    };
  }, [city, frames]);

  return <div className="map" ref={host} title="Drag to pan, scroll to zoom, double-click to fit, click a person or building" />;
}

// ---- static drawing ------------------------------------------------------------------------------

function drawGround(g: Graphics, city: City) {
  g.rect(-FAR, -FAR, 2 * FAR, 2 * FAR).fill(PALETTE.undeveloped);
  // faint hand-drawn field strokes on the empty land around the city
  for (let k = 0; k < 260; k++) {
    const x = -300 + hash01(k, 11) * (city.size + 600);
    const y = -300 + hash01(k, 12) * (city.size + 600);
    g.moveTo(x, y).lineTo(x + 14 + 10 * hash01(k, 13), y - 3);
  }
  g.stroke({ width: 1.2, color: PALETTE.grassDark, alpha: 0.35 });
  // lots: each building sits on a pavement or lawn
  for (const b of city.buildings) {
    const park = b.kind === "park";
    g.roundRect(b.x - 7, b.y - 7, b.w + 14, b.h + 14, 4).fill(park ? PALETTE.grass : PALETTE.sidewalk);
  }
  // zoned plots waiting for a builder, and streets being laid
  const zoneTint: Record<string, number> = { residential: 0x9fc46a, commercial: 0x6f9fd0, industrial: 0x9a8f80 };
  for (const p of city.plots ?? []) {
    g.rect(p.x, p.y, p.w, p.h).fill({ color: zoneTint[p.zone] ?? 0xcccccc, alpha: 0.28 }).stroke({ width: 2, color: zoneTint[p.zone] ?? 0xcccccc, alpha: 0.9 });
  }
  for (const r of city.roadworks ?? []) {
    g.rect(r.x, r.y, r.w, r.h).stroke({ width: 18, color: 0xb48d5e, alpha: 0.9 });
    for (let d = 0; d < r.w; d += 30) {
      for (const [x, y] of [[r.x + d, r.y], [r.x + d, r.y + r.h], [r.x, r.y + d], [r.x + r.w, r.y + d]]) g.circle(x, y, 3).fill(0xf08a24);
    }
  }
  const byId = new Map(city.nodes.map((n) => [n.id, n]));
  const seg = (fn: (ax: number, ay: number, bx: number, by: number) => void) => {
    for (const [a, b] of city.edges) {
      const na = byId.get(a)!;
      const nb = byId.get(b)!;
      fn(na.x, na.y, nb.x, nb.y);
    }
  };
  seg((ax, ay, bx, by) => g.moveTo(ax, ay).lineTo(bx, by));
  g.stroke({ width: 24, color: PALETTE.roadEdge, cap: "round", join: "round" });
  seg((ax, ay, bx, by) => g.moveTo(ax, ay).lineTo(bx, by));
  g.stroke({ width: 20, color: PALETTE.road, cap: "round", join: "round" });
  // dashed centre lines, drawn as short strokes
  seg((ax, ay, bx, by) => {
    const len = Math.hypot(bx - ax, by - ay);
    const ux = (bx - ax) / len;
    const uy = (by - ay) / len;
    for (let d = 20; d < len - 20; d += 22) g.moveTo(ax + ux * d, ay + uy * d).lineTo(ax + ux * (d + 10), ay + uy * (d + 10));
  });
  g.stroke({ width: 1.6, color: PALETTE.roadLine, alpha: 0.8 });
  for (const n of city.nodes) g.circle(n.x, n.y, 11).fill(PALETTE.road);
  // parks: trees, and in the biggest one LotusLab's pond
  const parks = city.buildings.filter((b) => b.kind === "park");
  const central = parks.reduce<Building | null>((m, b) => (!m || b.w * b.h > m.w * m.h ? b : m), null);
  for (const p of parks) {
    const cx = p.x + p.w / 2;
    const cy = p.y + p.h / 2;
    const pond = p === central || hash01(p.id, 3) < 0.5;
    if (pond) {
      const rx = p.w * 0.27;
      const ry = p.h * 0.2;
      g.ellipse(cx, cy, rx + 4, ry + 4).fill(0xb9c99a);
      g.ellipse(cx, cy, rx, ry).fill(PALETTE.water);
      g.ellipse(cx - rx * 0.15, cy - ry * 0.1, rx * 0.6, ry * 0.55).fill({ color: PALETTE.waterDeep, alpha: 0.5 });
      for (let k = 0; k < 9; k++) {
        const a = hash01(p.id * 31 + k, 4) * Math.PI * 2;
        const rr = 0.35 + 0.5 * hash01(p.id * 31 + k, 5);
        const lx = cx + Math.cos(a) * rx * rr;
        const ly = cy + Math.sin(a) * ry * rr;
        g.circle(lx, ly, 5).fill(PALETTE.lotusPad);
        if (k % 3 === 0) g.circle(lx + 1, ly - 1, 2.2).fill(PALETTE.lotusFlower);
      }
    }
    const trees = Math.round((p.w * p.h) / 1400);
    for (let k = 0; k < trees; k++) {
      const tx = p.x + 8 + hash01(p.id * 97 + k, 6) * (p.w - 16);
      const ty = p.y + 8 + hash01(p.id * 97 + k, 7) * (p.h - 16);
      if (pond && ((tx - cx) / (p.w * 0.33)) ** 2 + ((ty - cy) / (p.h * 0.26)) ** 2 < 1) continue;
      const tr = 6 + 4 * hash01(p.id * 97 + k, 8);
      g.ellipse(tx + 4, ty + 4, tr, tr * 0.6).fill({ color: PALETTE.shadow, alpha: 0.18 });
      g.circle(tx, ty, tr).fill(PALETTE.treeDark);
      g.circle(tx - tr * 0.25, ty - tr * 0.3, tr * 0.7).fill(PALETTE.tree);
    }
  }
}

function drawBuilding(g: Graphics, b: Building, height: number) {
  if (b.status === "construction") {
    // a building site: bare earth, a rising frame, and a crane
    g.rect(b.x, b.y, b.w, b.h).fill(0xc9a273).stroke({ width: 2, color: 0x3f6fb5 });
    for (let k = 8; k < b.w + b.h; k += 10) {
      g.moveTo(b.x + Math.max(0, k - b.h), b.y + Math.min(k, b.h)).lineTo(b.x + Math.min(k, b.w), b.y + Math.max(0, k - b.w));
    }
    g.stroke({ width: 1, color: 0x8c6239, alpha: 0.35 });
    const tx = b.x + b.w * 0.15;
    const ty = b.y + b.h * 0.2;
    g.moveTo(tx, ty + 10).lineTo(tx, ty - 34).lineTo(tx + b.w * 0.8, ty - 34).moveTo(tx - 10, ty - 34).lineTo(tx, ty - 34);
    g.stroke({ width: 3, color: 0xf2b32a });
    g.moveTo(tx + b.w * 0.5, ty - 34).lineTo(tx + b.w * 0.5, ty - 10).stroke({ width: 1, color: PALETTE.ink });
    return;
  }
  if (b.kind === "park") return;
  const kind = styleKind(b);
  const roof = ROOF[kind] ?? 0xcccccc;
  const z = height * LIFT;
  const ink = { width: 1.1, color: PALETTE.ink, alpha: 0.55 };
  if (WORSHIP_KINDS.includes(kind)) {
    // a low compound wall in the worship colour, so every faith's place reads as one family on the map
    g.poly(flat(wobblyRect(b.x - 4, b.y - 4, b.w + 8, b.h + 8, b.id * 3 + 5, 0.8))).stroke({ width: 3, color: ROOF.worship, alpha: 0.85 });
  }
  // front wall, then the roof on top of it, both with a slight hand-drawn wobble
  const wall = wobblyRect(b.x, b.y + b.h - z, b.w, z, b.id * 3 + 1, 0.8);
  g.poly(flat(wall)).fill(shade(roof, 0.7)).stroke(ink);
  for (const w of windowGrid(b, height)) g.rect(w.x, w.y, w.w, w.h).fill({ color: PALETTE.window, alpha: 0.55 });
  if (kind === "shop" || kind === "restaurant") {
    // striped awning over the shop front
    const ay = b.y + b.h - z;
    const stripes = Math.max(3, Math.floor(b.w / 10));
    for (let k = 0; k < stripes; k++) {
      g.rect(b.x + (k * b.w) / stripes, ay, b.w / stripes, Math.min(5, z * 0.4)).fill(k % 2 ? 0xfff3df : kind === "shop" ? 0x3f8f6a : 0xb5402f);
    }
  }
  const top = wobblyRect(b.x, b.y - z, b.w, b.h, b.id * 3 + 2, 1.0);
  g.poly(flat(top)).fill(roof).stroke(ink);
  // roof details
  const cx = b.x + b.w / 2;
  const cy = b.y - z + b.h / 2;
  const s = Math.min(b.w, b.h) * 0.28;
  switch (kind) {
    case "home":
      g.moveTo(b.x + 3, cy).lineTo(b.x + b.w - 3, cy).stroke({ width: 1.4, color: shade(roof, 0.75) });
      g.rect(b.x + b.w * 0.7, b.y - z + 4, 5, 5).fill(shade(roof, 0.6)); // chimney
      break;
    case "apartment":
      g.rect(b.x + 6, b.y - z + 6, b.w - 12, b.h - 12).stroke({ width: 1, color: shade(roof, 0.8) });
      break;
    case "office":
      g.rect(cx - b.w * 0.18, cy - b.h * 0.18, b.w * 0.36, b.h * 0.36).fill(shade(roof, 0.85)).stroke(ink);
      g.circle(cx + b.w * 0.3, cy - b.h * 0.3, 2).fill(0xd9480f);
      break;
    case "factory": {
      const teeth = Math.max(3, Math.floor(b.w / 14));
      for (let k = 0; k < teeth; k++) {
        const x0 = b.x + (k * b.w) / teeth;
        g.poly([x0, cy + 6, x0 + b.w / teeth, cy + 6, x0 + b.w / teeth, cy - 6]).fill(shade(roof, 0.82));
      }
      g.rect(b.x + b.w - 12, b.y - z - 10, 7, 16).fill(0x8a7f74).stroke(ink); // chimney
      break;
    }
    case "hospital":
      g.rect(cx - 3, cy - 10, 6, 20).fill(0xd2463c);
      g.rect(cx - 10, cy - 3, 20, 6).fill(0xd2463c);
      break;
    case "city_hall":
      g.circle(cx, cy, Math.min(b.w, b.h) * 0.22).fill(0xf6e3a3).stroke(ink);
      g.circle(cx - 3, cy - 3, Math.min(b.w, b.h) * 0.08).fill({ color: 0xffffff, alpha: 0.7 });
      break;
    case "police":
      g.star(cx, cy, 5, Math.min(b.w, b.h) * 0.18).fill(0xf2d16b).stroke(ink);
      break;
    case "bank":
      for (let k = 0; k < 5; k++) g.rect(b.x + 8 + k * ((b.w - 16) / 5), cy - 8, 3, 16).fill(0xeef6ee);
      break;
    case "school":
      g.circle(cx, cy, 4).fill(0xffffff).stroke(ink);
      g.moveTo(cx, cy).lineTo(cx, cy - 3).stroke({ width: 1, color: PALETTE.ink });
      break;
    case "temple":
      shikhara(g, cx, cy + s * 0.25, s, roof, ink, 0xf08a24);
      break;
    case "derasar":
      shikhara(g, cx - s * 0.75, cy + s * 0.35, s * 0.55, roof, ink, 0xd2463c);
      shikhara(g, cx + s * 0.75, cy + s * 0.35, s * 0.55, roof, ink, 0xd2463c);
      shikhara(g, cx, cy + s * 0.2, s * 0.8, roof, ink, 0xd2463c);
      break;
    case "mosque": {
      // a dome with a finial, and a slender minaret at the corner
      g.ellipse(cx + 2, cy + s * 0.25, s * 0.75, s * 0.3).fill({ color: PALETTE.shadow, alpha: 0.18 });
      g.circle(cx, cy, s * 0.7).fill(0xf7f3ea).stroke(ink);
      g.circle(cx - s * 0.22, cy - s * 0.25, s * 0.22).fill({ color: 0xffffff, alpha: 0.8 });
      g.moveTo(cx, cy - s * 0.7).lineTo(cx, cy - s * 1.0).stroke({ width: 1.4, color: 0xc9a227 });
      g.circle(cx, cy - s * 1.05, 2).fill(0xc9a227);
      const mx = b.x + 8;
      const my = b.y - z + 8;
      g.rect(mx - 3, my - 26, 6, 30).fill(0xf7f3ea).stroke(ink);
      g.rect(mx - 4.5, my - 18, 9, 3).fill(shade(roof, 0.8));
      g.poly([mx - 3.5, my - 26, mx + 3.5, my - 26, mx, my - 33]).fill(0x5e9b6f).stroke(ink);
      break;
    }
    case "church": {
      // a bell tower at the front with a pointed roof and a cross
      const tx = cx;
      const ty = b.y - z + b.h * 0.72;
      g.rect(tx - 8, ty - 30, 16, 30).fill(shade(roof, 0.9)).stroke(ink);
      g.rect(tx - 3, ty - 24, 6, 8).fill(PALETTE.window);
      g.poly([tx - 10, ty - 30, tx + 10, ty - 30, tx, ty - 48]).fill(0x6b7f99).stroke(ink);
      g.moveTo(tx, ty - 48).lineTo(tx, ty - 58).moveTo(tx - 4, ty - 54).lineTo(tx + 4, ty - 54).stroke({ width: 1.6, color: PALETTE.ink });
      g.moveTo(b.x + 4, cy - b.h * 0.15).lineTo(b.x + b.w - 4, cy - b.h * 0.15).stroke({ width: 1.2, color: shade(roof, 0.75) });
      break;
    }
    case "gurudwara": {
      // white walls, a golden dome, and the Nishan Sahib flag on its tall pole
      g.circle(cx, cy, s * 0.62).fill(0xf2c94c).stroke(ink);
      g.circle(cx - s * 0.2, cy - s * 0.22, s * 0.18).fill({ color: 0xfff3c4, alpha: 0.9 });
      g.circle(cx, cy - s * 0.7, 2.5).fill(0xe0b030);
      for (const dx of [-1, 1]) g.circle(cx + dx * b.w * 0.36, b.y - z + 7, 4).fill(0xf2c94c).stroke(ink);
      const px = b.x + b.w - 8;
      const py = b.y - z + b.h - 6;
      g.moveTo(px, py).lineTo(px, py - 46).stroke({ width: 1.6, color: 0x6b6b6b });
      g.poly([px, py - 46, px - 14, py - 41, px, py - 36]).fill(0xf08a24).stroke(ink);
      break;
    }
    case "vihara": {
      // a white stupa: a dome, a small square harmika and a spire
      g.ellipse(cx + 2, cy + s * 0.3, s * 0.8, s * 0.3).fill({ color: PALETTE.shadow, alpha: 0.18 });
      g.circle(cx, cy, s * 0.72).fill(0xfbf8f0).stroke(ink);
      g.rect(cx - 4, cy - s * 0.72 - 6, 8, 6).fill(0xe6dcc4).stroke(ink);
      g.poly([cx - 3, cy - s * 0.72 - 6, cx + 3, cy - s * 0.72 - 6, cx, cy - s * 0.72 - 20]).fill(0xd9a933);
      break;
    }
    case "agiary":
      // a quiet stone hall around a courtyard with its sacred fire
      g.rect(cx - b.w * 0.2, cy - b.h * 0.2, b.w * 0.4, b.h * 0.4).fill(shade(roof, 0.85)).stroke(ink);
      g.circle(cx, cy + 2, 4).fill(0xf08a24);
      g.circle(cx, cy - 1, 2.6).fill(0xffd27a);
      break;
    default:
      break;
  }
}

/** A Hindu or Jain temple spire: a tapering tower in bands, a kalash on top and a small flag. */
function shikhara(g: Graphics, cx: number, base: number, s: number, roof: number, ink: { width: number; color: number; alpha: number }, flag: number) {
  const h = s * 1.9;
  g.ellipse(cx + 3, base, s * 0.9, s * 0.25).fill({ color: PALETTE.shadow, alpha: 0.2 });
  g.poly([cx - s * 0.75, base, cx + s * 0.75, base, cx + s * 0.25, base - h, cx - s * 0.25, base - h]).fill(shade(roof, 0.92)).stroke(ink);
  for (let k = 1; k < 4; k++) {
    const y = base - (h * k) / 4;
    const half = s * (0.75 - 0.5 * (k / 4));
    g.moveTo(cx - half, y).lineTo(cx + half, y).stroke({ width: 1, color: shade(roof, 0.7) });
  }
  g.poly([cx - s * 0.25, base - h, cx + s * 0.25, base - h, cx, base - h - s * 0.35]).fill(shade(roof, 0.8)).stroke(ink);
  g.circle(cx, base - h - s * 0.4, Math.max(1.6, s * 0.08)).fill(0xd9a933);
  g.moveTo(cx, base - h - s * 0.4).lineTo(cx, base - h - s * 0.4 - 12).stroke({ width: 1.2, color: 0x6b6b6b });
  g.poly([cx, base - h - s * 0.4 - 12, cx + 9, base - h - s * 0.4 - 9, cx, base - h - s * 0.4 - 6]).fill(flag);
}

function drawLitWindows(g: Graphics, b: Building, height: number) {
  for (const w of windowGrid(b, height)) {
    if (hash01(b.id * 1000 + w.key, 9) < 0.35) continue; // not every room has the lights on
    g.rect(w.x - 1, w.y - 1, w.w + 2, w.h + 2).fill({ color: PALETTE.windowLit, alpha: 0.35 });
    g.rect(w.x, w.y, w.w, w.h).fill(PALETTE.windowLit);
  }
}

let grainTexture: Texture | null = null;

/** A small tile of paper fibres and speckles, generated once. */
function paperGrain(): Texture {
  if (grainTexture) return grainTexture;
  const c = document.createElement("canvas");
  c.width = c.height = 256;
  const ctx = c.getContext("2d")!;
  const img = ctx.createImageData(256, 256);
  for (let i = 0; i < 256 * 256; i++) {
    const v = 128 + (hash01(i, 21) - 0.5) * 120;
    img.data[i * 4] = v;
    img.data[i * 4 + 1] = v * 0.95;
    img.data[i * 4 + 2] = v * 0.85;
    img.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
  ctx.strokeStyle = "rgba(90,70,50,0.25)";
  for (let k = 0; k < 40; k++) {
    const x = hash01(k, 22) * 256;
    const y = hash01(k, 23) * 256;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + 6 + hash01(k, 24) * 14, y + (hash01(k, 25) - 0.5) * 6);
    ctx.stroke();
  }
  grainTexture = Texture.from(c);
  return grainTexture;
}
