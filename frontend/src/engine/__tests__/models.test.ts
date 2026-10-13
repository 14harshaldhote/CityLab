import { describe, expect, it } from "vitest";
import type { Building, CityMap } from "../../api/types";
import { buildingModel, outskirtsModel, plotModel, siteHeight, siteModel, streetModel, transitModel } from "../models";

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

  it("turns a building under construction into a site with a crane taller than the finished block", () => {
    const b: Building = { ...lot(5, "home", 0), status: "construction", progress: 0.3, planned: 10 };
    const m = buildingModel(b);
    expect(m.windows).toHaveLength(0);
    expect(m.parts.every((p) => p.bid === 5)).toBe(true);
    const mast = Math.max(...m.parts.map((p) => p.y + p.h));
    expect(mast).toBeGreaterThan(siteHeight(b));
    expect(siteModel(b).parts.length).toBe(m.parts.length);
  });

  it("marks zoned plots and lines new streets with cones", () => {
    const city: CityMap = {
      name: "Kamalnagar", size: 520, spacing: 260, districts: [], activities: [], nodes: [], edges: [], buildings: [],
      plots: [{ x: 10, y: 10, w: 104, h: 104, zone: "residential", district: "Nadi Kinara" }],
      roadworks: [{ x: 0, y: 0, w: 260, h: 260 }],
    };
    const parts = plotModel(city);
    expect(parts.filter((p) => p.c === 0xcfe6a8)).toHaveLength(1);
    expect(parts.filter((p) => p.s === "cone").length).toBeGreaterThan(30);
    expect(parts.every((p) => p.bid === -1)).toBe(true);
  });

  it("puts a shelter and a sign in each route's colour at every bus stop", () => {
    const city: CityMap = {
      name: "Kamalnagar", size: 520, spacing: 260, districts: [], activities: [], nodes: [], edges: [], buildings: [],
      transit: {
        lines: [
          { number: "1", name: "A to B", color: "#d2463c", nodes: [0, 1], stops: [0] },
          { number: "2", name: "C to D", color: "#2c7fb8", nodes: [0, 2], stops: [0] },
        ],
        stops: [{ id: 0, name: "Kamal Chowk", x: 260, y: 260, node: 0, lines: ["1", "2"] }],
      },
    };
    const parts = transitModel(city);
    expect(parts.some((p) => p.c === 0xd2463c)).toBe(true);
    expect(parts.some((p) => p.c === 0x2c7fb8)).toBe(true);
    for (const p of parts) expect(Math.hypot(p.x - 260, p.z - 260)).toBeLessThan(60);
  });

  it("draws widened streets wider, with a divider, and cones while the work goes on", () => {
    const base: CityMap = {
      name: "Kamalnagar", size: 520, spacing: 260, districts: [], activities: [],
      nodes: [{ id: 0, x: 0, y: 0 }, { id: 1, x: 260, y: 0 }], edges: [[0, 1]], buildings: [],
    };
    const road = (c: CityMap) => streetModel(c).parts.find((p) => p.c === 0x5b5754 && p.w === 260)!;
    expect(road(base).d).toBe(20);
    expect(road({ ...base, wide: [[1, 0]] }).d).toBe(30);
    expect(streetModel({ ...base, widening: [[0, 1]] }).parts.filter((p) => p.s === "cone").length).toBeGreaterThan(20);
  });
});
