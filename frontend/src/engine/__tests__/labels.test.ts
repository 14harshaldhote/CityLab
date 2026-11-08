import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Building } from "../../api/types";
import { BuildingLabels, shortName, type Spot } from "../labels";

// just enough of a page for the tags: elements that hold text, a style and a size
class FakeEl {
  children: FakeEl[] = [];
  style: Record<string, string> = {};
  className = "";
  textContent = "";
  classes = new Set<string>();
  classList = { toggle: (c: string, on: boolean) => (on ? this.classes.add(c) : this.classes.delete(c)) };
  get offsetWidth() {
    return this.textContent.length * 6 + 20;
  }
  offsetHeight = 18;
  appendChild(c: FakeEl) {
    this.children.push(c);
  }
  remove() {}
  closest() {
    return null;
  }
  querySelectorAll() {
    return [] as FakeEl[];
  }
  getBoundingClientRect() {
    return { left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600 };
  }
}

const b = (id: number, kind: string, name: string) => ({ id, kind, name, x: 0, y: 0, w: 100, h: 100, district: "Kamal Chowk" }) as unknown as Building;
const shown = (host: FakeEl) => host.children[0].children.filter((t) => t.style.display !== "none").map((t) => t.textContent);

describe("building name tags", () => {
  let host: FakeEl;
  beforeEach(() => {
    (globalThis as { document?: unknown }).document = { createElement: () => new FakeEl() };
    host = new FakeEl();
  });
  afterEach(() => {
    delete (globalThis as { document?: unknown }).document;
  });

  it("shows the short name, without the district", () => {
    expect(shortName(b(1, "clinic", "Sanjeevani Clinic, Paschim Peth"))).toBe("Sanjeevani Clinic");
  });

  it("lets the more important place win when two tags would overlap", () => {
    const labels = new BuildingLabels(host as unknown as HTMLElement);
    const spots: Spot[] = [
      { b: b(1, "shop", "Ganesh Kirana, Nadi Kinara"), x: 400, y: 300, rank: 20 },
      { b: b(2, "hospital", "Kamalnagar Civil Hospital"), x: 410, y: 305, rank: 90 },
      { b: b(3, "temple", "Ram Mandir"), x: 100, y: 100, rank: 50 },
    ];
    labels.place(spots, 800, 600, null);
    expect(shown(host).sort()).toEqual(["Kamalnagar Civil Hospital", "Ram Mandir"]);
  });

  it("never shows a tag cut off at the edge, and hides tags that leave the screen", () => {
    const labels = new BuildingLabels(host as unknown as HTMLElement);
    const temple = b(3, "temple", "Ram Mandir");
    labels.place([{ b: temple, x: 100, y: 100, rank: 50 }], 800, 600, null);
    expect(shown(host)).toEqual(["Ram Mandir"]);
    labels.place([{ b: temple, x: 5, y: 100, rank: 50 }], 800, 600, null);
    expect(shown(host)).toEqual([]);
    labels.place([{ b: temple, x: 100, y: 100, rank: 50 }], 800, 600, null);
    expect(shown(host)).toEqual(["Ram Mandir"]);
    labels.hide();
    expect(shown(host)).toEqual([]);
  });

  it("marks the building you picked", () => {
    const labels = new BuildingLabels(host as unknown as HTMLElement);
    labels.place([{ b: b(7, "bank", "City Bank"), x: 300, y: 300, rank: 1000 }], 800, 600, 7);
    expect(host.children[0].children[0].classes.has("picked")).toBe(true);
  });
});
