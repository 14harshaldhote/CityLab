import type { Building } from "../api/types";

/** How much a kind of place deserves a name tag when space is short: the bigger, the sooner. */
export const LANDMARK: Record<string, number> = {
  hospital: 9,
  city_hall: 9,
  court: 8,
  police: 8,
  bus_depot: 7,
  bank: 7,
  clinic: 6,
  school: 6,
  temple: 5,
  mosque: 5,
  church: 5,
  gurudwara: 5,
  derasar: 5,
  vihara: 5,
  agiary: 5,
  park: 4,
};
const GROUP: Record<string, string> = {
  hospital: "care",
  clinic: "care",
  police: "safety",
  court: "civic",
  city_hall: "civic",
  bank: "civic",
  bus_depot: "civic",
  school: "school",
  park: "park",
  shop: "trade",
  restaurant: "trade",
  office: "work",
  factory: "work",
  home: "home",
};

/** "Sanjeevani Clinic, Paschim Peth" is shown as "Sanjeevani Clinic". */
export const shortName = (b: Building) => b.name.split(",")[0];

export interface Spot {
  b: Building;
  x: number; // screen pixels: where the bottom of the tag points
  y: number;
  rank: number; // higher is placed first
}

const MAX_TAGS = 70;
const GAP = 3;
const POINTER = 6; // the little arrow under each tag

/**
 * Name tags for buildings, laid over a map as plain text so they stay sharp at any zoom.
 * Each frame the caller says where every candidate building sits on screen; the most
 * important ones are placed first, and any tag that would overlap one already placed is
 * left out, so the map never turns into a pile of words.
 */
export class BuildingLabels {
  private layer: HTMLDivElement;
  private tags = new Map<number, { el: HTMLDivElement; w: number; h: number; x: number; y: number; on: boolean }>();

  constructor(private host: HTMLElement) {
    this.layer = document.createElement("div");
    this.layer.className = "b-labels";
    host.appendChild(this.layer);
  }

  private tag(b: Building) {
    let t = this.tags.get(b.id);
    if (!t) {
      const el = document.createElement("div");
      const land = b.kind in LANDMARK;
      el.className = `b-label g-${GROUP[b.kind] ?? (land ? "faith" : "work")}${land ? " land" : ""}`;
      el.textContent = shortName(b);
      this.layer.appendChild(el);
      t = { el, w: el.offsetWidth || shortName(b).length * 6.5 + 20, h: el.offsetHeight || 20, x: NaN, y: NaN, on: true };
      this.tags.set(b.id, t);
    }
    return t;
  }

  place(spots: Spot[], width: number, height: number, selected: number | null) {
    spots.sort((a, c) => c.rank - a.rank);
    const placed: number[] = []; // x0, y0, x1, y1 of every tag already down
    // keep clear of the buttons, the map key and the voices floating over the map
    const box = this.host.getBoundingClientRect();
    const over = (this.host.closest(".stage") ?? this.host).querySelectorAll(".view-switch, .view-tools, .voice-ticker, .map-legend");
    over.forEach((o) => {
      const r = o.getBoundingClientRect();
      if (r.width > 0) placed.push(r.left - box.left, r.top - box.top, r.right - box.left, r.bottom - box.top);
    });
    const keep = new Set<number>();
    for (const s of spots) {
      if (keep.size >= MAX_TAGS) break;
      if (s.x < -40 || s.y < 0 || s.x > width + 40 || s.y > height + 30) continue;
      const t = this.tag(s.b);
      const x0 = s.x - t.w / 2 - GAP;
      const y0 = s.y - t.h - POINTER - GAP;
      const x1 = s.x + t.w / 2 + GAP;
      const y1 = s.y + GAP;
      if (x0 < 0 || y0 < 0 || x1 > width || y1 > height) continue; // only whole tags, never one cut off at the edge
      let clash = false;
      for (let i = 0; i < placed.length && !clash; i += 4) {
        clash = x0 < placed[i + 2] && x1 > placed[i] && y0 < placed[i + 3] && y1 > placed[i + 1];
      }
      if (clash) continue;
      placed.push(x0, y0, x1, y1);
      keep.add(s.b.id);
      const x = Math.round(s.x - t.w / 2);
      const y = Math.round(s.y - t.h - POINTER);
      if (x !== t.x || y !== t.y) {
        t.x = x;
        t.y = y;
        t.el.style.transform = `translate(${x}px, ${y}px)`;
      }
      t.el.classList.toggle("picked", s.b.id === selected);
    }
    for (const [id, t] of this.tags) {
      const on = keep.has(id);
      if (on !== t.on) {
        t.on = on;
        t.el.style.display = on ? "" : "none";
      }
    }
  }

  hide() {
    this.place([], 0, 0, null);
  }

  destroy() {
    this.layer.remove();
    this.tags.clear();
  }
}
