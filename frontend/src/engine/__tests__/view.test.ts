import { describe, expect, it } from "vitest";
import { agoLabel, lerpFrames, nearestPoint, rectAt, simLabel } from "../view";

describe("view helpers", () => {
  it("finds the nearest point within a radius", () => {
    const xs = [0, 10, 20];
    const ys = [0, 0, 0];
    expect(nearestPoint(xs, ys, 9, 1, 5)).toBe(1);
    expect(nearestPoint(xs, ys, 50, 50, 5)).toBe(-1);
  });

  it("picks the rectangle under a point", () => {
    const rects = [
      { id: 1, x: 0, y: 0, w: 10, h: 10 },
      { id: 2, x: 20, y: 0, w: 10, h: 10 },
    ];
    expect(rectAt(rects, 25, 5)?.id).toBe(2);
    expect(rectAt(rects, 15, 5)).toBeUndefined();
  });

  it("interpolates matching ids and snaps new ones", () => {
    const out = { x: new Float32Array(2), y: new Float32Array(2) };
    lerpFrames({ ids: [1], x: [0], y: [0] }, { ids: [1, 2], x: [10, 5], y: [20, 5] }, 0.5, out);
    expect(Array.from(out.x)).toEqual([5, 5]);
    expect(Array.from(out.y)).toEqual([10, 5]);
  });

  it("writes simulation time the way the city does", () => {
    expect(simLabel(0)).toBe("Thu 01 Jan 2026 00:00");
    expect(simLabel(1440 + 600)).toBe("Fri 02 Jan 2026 10:00");
    expect(simLabel(365 * 1440 + 61)).toBe("Fri 01 Jan 2027 01:01");
    expect(agoLabel(90)).toBe("2 h ago");
    expect(agoLabel(1440)).toBe("a day ago");
    expect(agoLabel(3 * 1440)).toBe("3 days ago");
  });
});
