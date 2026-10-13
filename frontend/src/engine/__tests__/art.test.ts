import { describe, expect, it } from "vitest";
import type { Summary } from "../../api/types";
import { advise } from "../advisor";
import { PEOPLE, ROOF, WORSHIP_KINDS, buildingHeight, convexHull, daylight, hash01, shadowPolygon, styleKind, windowGrid } from "../art";

const box = { id: 7, kind: "office", x: 100, y: 100, w: 50, h: 40, district: "Kamal Chowk", central: true };

describe("art", () => {
  it("is deterministic per building", () => {
    expect(hash01(5, 1)).toBe(hash01(5, 1));
    expect(hash01(5, 1)).not.toBe(hash01(6, 1));
    expect(buildingHeight(box)).toBe(buildingHeight({ ...box }));
  });

  it("makes downtown offices taller than houses", () => {
    expect(buildingHeight(box)).toBeGreaterThan(buildingHeight({ ...box, kind: "home", households: 2 }));
    expect(styleKind({ ...box, kind: "home", households: 8 })).toBe("apartment");
  });

  it("casts no shadow at night and points shadows away from the sun", () => {
    expect(shadowPolygon(box, 50, -5, 180)).toBeNull();
    // sun in the south at noon: shadow falls north (smaller y)
    const noon = shadowPolygon(box, 50, 45, 180)!;
    expect(Math.min(...noon.map((p) => p[1]))).toBeLessThan(box.y - 10);
    // morning sun in the east: shadow falls west (smaller x)
    const morning = shadowPolygon(box, 50, 20, 90)!;
    expect(Math.min(...morning.map((p) => p[0]))).toBeLessThan(box.x - 50);
  });

  it("builds a convex hull", () => {
    const hull = convexHull([
      [0, 0],
      [2, 0],
      [1, 1],
      [2, 2],
      [0, 2],
    ]);
    expect(hull).toHaveLength(4);
  });

  it("puts windows on the front wall only for real buildings", () => {
    expect(windowGrid({ ...box, kind: "park" }, 0)).toHaveLength(0);
    const ws = windowGrid(box, 80);
    expect(ws.length).toBeGreaterThan(4);
    for (const w of ws) expect(w.y + w.h).toBeLessThanOrEqual(box.y + box.h);
  });

  it("draws every place of worship, and gives worshippers their own colour", () => {
    for (const kind of WORSHIP_KINDS) {
      expect(ROOF[kind]).toBeDefined();
      expect(buildingHeight({ ...box, kind })).toBeGreaterThan(0);
    }
    expect(PEOPLE).toHaveLength(12); // one colour per activity, the last for people in jail
  });

  it("is dark at night and bright at noon", () => {
    expect(daylight(-20, 0)).toBe(0);
    expect(daylight(60, 0)).toBe(1);
  });
});

describe("advisor", () => {
  const base: Summary = {
    t: 0, label: "", population: 1000, households: 400, employed: 500, unemployed: 100, pupils: 200, retired: 100, couples: 200,
    vacancies: 20, free_homes: 5, social: { people: 1000, ties: 5000, friendships: 4000, avg_ties: 10 }, events: 0, playing: true,
    speed: 10, step_ms: 1, seed: 1, city: "Kamalnagar", religions: { Hindu: 780, Muslim: 120 }, festival: null,
  };

  it("flags full housing and high unemployment first", () => {
    const tips = advise(base, null, []);
    expect(tips[0].tone).toBe("act");
    expect(tips.map((t) => t.title)).toContain("Homes are almost full");
    expect(tips.some((t) => t.title.includes("out of work"))).toBe(true);
  });

  it("says nothing without data", () => {
    expect(advise(null, null, [])).toEqual([]);
  });
});
