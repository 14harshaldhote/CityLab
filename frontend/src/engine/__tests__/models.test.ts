import { describe, expect, it } from "vitest";
import type { Building, CityMap } from "../../api/types";
import { buildingModel, outskirtsModel, streetModel } from "../models";

const kinds = ["home", "office", "shop", "restaurant", "factory", "school", "hospital", "police", "city_hall", "bank", "park", "bus_depot",
  "temple", "mosque", "church", "gurudwara", "vihara", "derasar", "agiary"];

const lot = (id: number, kind: string, households = 0): Building => ({
  id, kind, name: kind === "park" ? "Tilak Baug" : `${kind} ${id}`, x: 300, y: 300, w: 104, h: 104, district: "Phool Baug", households, jobs: 4,
});

describe("3D models", () => {
  it("builds every kind of building inside its own lot", () => {
    for (const [k, kind] of kinds.entries()) {
      const m = buildingModel(lot(k, kind, kind === "home" ? 3 : 0));
      expect(m.parts.length, kind).toBeGreaterThan(1);
      for (const p of m.parts) {
        if (p.bid >= 0) expect(p.bid).toBe(k);
        expect(Number.isFinite(p.x + p.y + p.z + p.w + p.h + p.d), kind).toBe(true);
        expect(p.x).toBeGreaterThan(290);
        expect(p.x).toBeLessThan(414);
      }
    }
  });

  it("gives housing societies windows and water tanks, and houses tiled roofs", () => {
    const flats = buildingModel(lot(1, "home", 8));
    expect(flats.windows.length).toBeGreaterThan(40);
    expect(flats.parts.filter((p) => p.s === "cyl").length).toBeGreaterThanOrEqual(3);
    expect(buildingModel(lot(2, "home", 3)).parts.some((p) => p.s === "roof")).toBe(true);
  });

  it("lays streets, lamps and farmland", () => {
    const city: CityMap = {
      name: "Kamalnagar", size: 520, spacing: 260, districts: [], activities: [],
      nodes: [{ id: 0, x: 0, y: 0 }, { id: 1, x: 260, y: 0 }, { id: 2, x: 0, y: 260 }],
      edges: [[0, 1], [0, 2]],
      buildings: [lot(0, "home", 3)],
    };
    const s = streetModel(city);
    expect(s.lamps).toHaveLength(3);
    expect(s.parts.some((p) => p.c === 0x5b5754 && p.w === 260)).toBe(true);
    expect(outskirtsModel(city, 1).length).toBeGreaterThan(5);
  });
});
