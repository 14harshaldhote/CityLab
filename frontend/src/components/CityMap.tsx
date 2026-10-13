import { Application, Container, Graphics } from "pixi.js";
import { useEffect, useRef } from "react";
import type { CityMap as City, Frame } from "../api/types";
import { ACTIVITY_COLORS, BUILDING_COLORS, lerpFrames, nearestPoint, nightShade, rectAt } from "../engine/view";

interface Props {
  city: City;
  frames: React.MutableRefObject<{ prev: Frame | null; next: Frame | null; at: number }>;
  selectedPerson: number | null;
  selectedBuilding: number | null;
  onPickPerson: (id: number) => void;
  onPickBuilding: (id: number) => void;
}

const TICK_MS = 200;

/**
 * The live map, drawn with PixiJS (WebGL). Streets and buildings are drawn once;
 * people are redrawn every animation frame, interpolated between the two most recent
 * server frames so they glide instead of jumping five times a second.
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
    const lamps = new Graphics();
    const shade = new Graphics();
    const people = new Graphics();
    const marks = new Graphics();
    world.addChild(ground, shade, lamps, people, marks);
    const pos = { x: new Float32Array(0), y: new Float32Array(0) };
    let shownIds: number[] = [];

    // ---- static layer: land, streets, buildings ------------------------------------
    const pad = 120;
    ground.rect(-20000, -20000, city.size + 40000, city.size + 40000).fill(0xdfe6d2);
    const byId = new Map(city.nodes.map((n) => [n.id, n]));
    for (const [a, b] of city.edges) {
      const na = byId.get(a)!;
      const nb = byId.get(b)!;
      ground.moveTo(na.x, na.y).lineTo(nb.x, nb.y);
    }
    ground.stroke({ width: 16, color: 0x8e9397, cap: "round" });
    for (const [a, b] of city.edges) {
      const na = byId.get(a)!;
      const nb = byId.get(b)!;
      ground.moveTo(na.x, na.y).lineTo(nb.x, nb.y);
    }
    ground.stroke({ width: 1.5, color: 0xd8d2b4 });
    for (const b of city.buildings) {
      ground.rect(b.x, b.y, b.w, b.h).fill(BUILDING_COLORS[b.kind] ?? 0xcccccc).stroke({ width: 1, color: 0x6f6a5f, alpha: 0.35 });
      if (b.kind === "park" && b.w > 150) {
        // the central park keeps LotusLab's pond
        ground.ellipse(b.x + b.w / 2, b.y + b.h / 2, b.w * 0.28, b.h * 0.2).fill(0x5d9fc8);
        for (let k = 0; k < 7; k++) {
          const a = (k / 7) * Math.PI * 2;
          ground.circle(b.x + b.w / 2 + Math.cos(a) * b.w * 0.16, b.y + b.h / 2 + Math.sin(a) * b.h * 0.1, 5).fill(0x3a9a55);
        }
      }
    }

    // ---- camera: fit, pan, zoom ---------------------------------------------------------
    const fit = () => {
      const s = Math.min(el.clientWidth, el.clientHeight) / (city.size + 2 * pad);
      world.scale.set(s);
      world.position.set((el.clientWidth - city.size * s) / 2, (el.clientHeight - city.size * s) / 2);
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
    const onUp = (e: PointerEvent) => {
      if (drag && !drag.moved) {
        const p = toWorld(e.clientX, e.clientY);
        const i = nearestPoint(pos.x, pos.y, p.x, p.y, 8 / world.scale.x);
        if (i >= 0 && i < shownIds.length) picks.current.onPickPerson(shownIds[i]);
        else {
          const b = rectAt(city.buildings, p.x, p.y);
          if (b) picks.current.onPickBuilding(b.id);
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

    // ---- per-frame drawing ------------------------------------------------------------------
    const draw = () => {
      const { prev, next, at } = frames.current;
      if (!next) return;
      if (pos.x.length !== next.ids.length) {
        pos.x = new Float32Array(next.ids.length);
        pos.y = new Float32Array(next.ids.length);
      }
      const f = Math.min(1, (performance.now() - at) / TICK_MS);
      if (prev) lerpFrames(prev, next, f, pos);
      else lerpFrames(next, next, 1, pos);
      shownIds = next.ids;

      const night = nightShade(next.weather.sun_elevation_deg, next.weather.cloud_pct);
      shade.clear();
      if (night > 0.01) shade.rect(-20000, -20000, city.size + 40000, city.size + 40000).fill({ color: 0x0b1030, alpha: night });
      lamps.clear();
      if (night > 0.25) {
        for (const n of city.nodes) lamps.circle(n.x, n.y, 7).fill({ color: 0xffd27a, alpha: 0.55 });
      }
      people.clear();
      const r = Math.max(3.2, 2.2 / world.scale.x);
      for (let i = 0; i < next.ids.length; i++) {
        people.circle(pos.x[i], pos.y[i], next.age[i] < 18 ? r * 0.75 : r).fill(ACTIVITY_COLORS[next.activity[i]] ?? 0x000000);
      }
      marks.clear();
      const { person, building } = sel.current;
      if (building !== null) {
        const b = city.buildings[building];
        if (b) marks.rect(b.x - 4, b.y - 4, b.w + 8, b.h + 8).stroke({ width: 4 / world.scale.x + 2, color: 0xd9480f });
      }
      if (person !== null) {
        const i = next.ids.indexOf(person);
        if (i >= 0) marks.circle(pos.x[i], pos.y[i], r * 3).stroke({ width: 3 / world.scale.x + 1, color: 0xd9480f });
      }
    };

    (async () => {
      await app.init({ resizeTo: el, background: 0xdfe6d2, antialias: true, autoDensity: true, resolution: window.devicePixelRatio || 1 });
      if (disposed) {
        app.destroy(true);
        return;
      }
      ready = true;
      el.appendChild(app.canvas);
      app.stage.addChild(world);
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
