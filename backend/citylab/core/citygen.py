"""Procedural city generator.

The city is a street grid with a few streets removed so it does not look like graph
paper. Blocks are zoned by distance from the centre and by direction: a downtown of
offices and shops, a civic quarter, an industrial edge, residential neighbourhoods,
parks, and a ring of empty land the city can grow into later. Every building hangs
off its nearest street corner, which is where routing starts and ends.

The city is Kamalnagar, an Indian city: its neighbourhoods have Marathi names, its
shops, schools and housing societies are named the way they are in India, and its
residential streets have places of worship for each community (see ``faith.py``).

Everything is drawn from one seed, so the same seed always builds the same city.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from .clock import MINUTES_PER_HOUR as H
from .names import CITY_NAME

# the eight neighbourhoods around the centre, by compass direction from west, then clockwise
DISTRICTS = ("Paschim Peth", "Shivaji Nagar", "Tekdi Wadi", "Talav Paar", "Girni Gaon", "Bazaar Peth", "Phool Baug", "Nadi Kinara")
CENTRE = "Kamal Chowk"


@dataclass(frozen=True, slots=True)
class Shift:
    start: int  # minute of day
    end: int  # minute of day, may be < start for night shifts
    weekdays_only: bool

    @property
    def length(self) -> int:
        return (self.end - self.start) % (24 * H) or 24 * H


@dataclass(frozen=True, slots=True)
class BuildingType:
    kind: str
    label: str
    jobs: int
    shifts: tuple[Shift, ...]
    wage: float  # per worked day
    open_from: int = 0
    open_to: int = 24 * H
    weekdays_only: bool = False


OFFICE_HOURS = (Shift(9 * H, 17 * H, True),)
TYPES: dict[str, BuildingType] = {
    t.kind: t
    for t in (
        BuildingType("home", "Homes", 0, (), 0.0),
        BuildingType("office", "Office", 30, OFFICE_HOURS, 160.0, 8 * H, 19 * H, True),
        BuildingType("shop", "Shop", 8, (Shift(9 * H + 30, 20 * H, False),), 95.0, 10 * H, 20 * H),
        BuildingType("restaurant", "Restaurant", 8, (Shift(11 * H, 23 * H, False),), 90.0, 11 * H, 23 * H),
        BuildingType("factory", "Factory", 30, (Shift(6 * H, 14 * H, False), Shift(14 * H, 22 * H, False)), 120.0),
        BuildingType("school", "School", 25, (Shift(7 * H + 30, 15 * H + 30, True),), 130.0, 8 * H, 15 * H, True),
        BuildingType(
            "hospital", "Hospital", 60, (Shift(7 * H, 15 * H, False), Shift(15 * H, 23 * H, False), Shift(23 * H, 7 * H, False)), 170.0
        ),
        BuildingType(
            "police", "Police station", 30, (Shift(6 * H, 14 * H, False), Shift(14 * H, 22 * H, False), Shift(22 * H, 6 * H, False)), 140.0
        ),
        BuildingType("city_hall", "City Hall", 40, OFFICE_HOURS, 150.0, 9 * H, 17 * H, True),
        BuildingType("bank", "Bank", 20, OFFICE_HOURS, 165.0, 9 * H, 17 * H, True),
        BuildingType("park", "Park", 2, (Shift(7 * H, 15 * H, False),), 80.0, 6 * H, 22 * H),
        BuildingType("bus_depot", "Bus depot", 20, (Shift(5 * H, 13 * H, False), Shift(13 * H, 21 * H, False)), 110.0),
        # places of worship: priests, caretakers and kitchen volunteers, paid by the trust from offerings
        BuildingType("temple", "Mandir", 4, (Shift(5 * H, 13 * H, False), Shift(13 * H, 21 * H, False)), 85.0, 5 * H, 21 * H + 30),
        BuildingType("mosque", "Masjid", 3, (Shift(4 * H + 30, 12 * H + 30, False), Shift(12 * H + 30, 21 * H, False)), 85.0, 4 * H + 30, 22 * H),
        BuildingType("church", "Church", 3, (Shift(6 * H, 14 * H, False), Shift(12 * H, 20 * H, False)), 85.0, 6 * H, 20 * H),
        BuildingType("gurudwara", "Gurudwara", 6, (Shift(4 * H, 12 * H, False), Shift(12 * H, 20 * H, False), Shift(20 * H, 4 * H, False)), 85.0),
        BuildingType("vihara", "Buddha Vihar", 2, (Shift(6 * H, 14 * H, False), Shift(13 * H, 21 * H, False)), 85.0, 6 * H, 21 * H),
        BuildingType("derasar", "Jain Derasar", 3, (Shift(5 * H + 30, 13 * H + 30, False), Shift(13 * H, 21 * H, False)), 85.0, 5 * H + 30, 21 * H),
        BuildingType("agiary", "Agiary", 2, (Shift(6 * H, 14 * H, False), Shift(13 * H, 21 * H, False)), 85.0, 6 * H, 21 * H),
    )
}


@dataclass(slots=True)
class Building:
    id: int
    kind: str
    name: str
    x: float
    y: float
    w: float
    h: float
    node: int  # nearest street corner
    district: str
    households: int = 0  # capacity, homes only
    students: int = 0  # capacity, schools only
    jobs: list[Shift] = field(default_factory=list)  # one entry per job slot
    status: str = "open"  # "construction" while it is being built
    progress: float = 1.0  # 0..1 while under construction
    owner: str = ""  # who built it (a developer, a trust, the city)
    opened_day: int = 0
    households_planned: int = 0  # homes it will have once finished
    zone: str = ""

    @property
    def type(self) -> BuildingType:
        return TYPES[self.kind]

    def is_open(self, minute_of_day: int, weekend: bool) -> bool:
        t = self.type
        if t.weekdays_only and weekend:
            return False
        if t.open_from <= t.open_to:
            return t.open_from <= minute_of_day < t.open_to
        return minute_of_day >= t.open_from or minute_of_day < t.open_to

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "w": round(self.w, 1),
            "h": round(self.h, 1),
            "district": self.district,
            "central": self.district == CENTRE,
            "households": self.households,
            "jobs": len(self.jobs),
            "status": self.status,
            "progress": round(self.progress, 3),
            "owner": self.owner,
            "opened_day": self.opened_day,
            "planned": self.households_planned,
        }


@dataclass
class City:
    size: float  # metres, the map is size x size
    spacing: float
    graph: nx.Graph  # street graph, node attrs x, y; edge attr length
    buildings: list[Building]
    developed: np.ndarray  # bool per block (n-1 x n-1)
    n: int  # corners per side
    name: str = CITY_NAME
    zones: dict[tuple[int, int], str] = field(default_factory=dict)  # zone of every developed block
    plots: list[Plot] = field(default_factory=list)  # zoned, empty lots waiting for a project
    roadworks: list[tuple[int, int]] = field(default_factory=list)  # blocks whose streets are being laid
    version: int = 0  # goes up whenever streets or buildings change
    def node_xy(self, node: int) -> tuple[float, float]:
        d = self.graph.nodes[node]
        return d["x"], d["y"]

    def of_kind(self, kind: str) -> list[Building]:
        return [b for b in self.buildings if b.kind == kind]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "size": self.size,
            "spacing": self.spacing,
            "nodes": [{"id": int(n), "x": d["x"], "y": d["y"]} for n, d in self.graph.nodes(data=True)],
            "edges": [[int(a), int(b)] for a, b in self.graph.edges()],
            "buildings": [b.to_dict() for b in self.buildings],
            "districts": list(DISTRICTS) + [CENTRE],
            "version": self.version,
            "plots": [p.to_dict() for p in self.plots],
            "roadworks": [self.block_rect(i, j) for i, j in self.roadworks],
        }

    def block_rect(self, i: int, j: int) -> dict:
        return {"x": i * self.spacing, "y": j * self.spacing, "w": self.spacing, "h": self.spacing}

    def block_of(self, b: Building) -> tuple[int, int]:
        return int(b.x // self.spacing), int(b.y // self.spacing)

    def district_at(self, i: int, j: int) -> str:
        c = (self.n - 2) / 2.0
        r, ang = math.hypot(i - c, j - c), math.atan2(j - c, i - c)
        return CENTRE if r < 1.8 else DISTRICTS[int(((ang + math.pi) / (2 * math.pi)) * 8) % 8]

    def lay_streets(self, i: int, j: int) -> int:
        """Streets around block (i, j), adding any missing corners. Returns how many street segments were new."""
        g = self.graph
        corner = lambda a, b: a * self.n + b  # noqa: E731
        for a, b in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)):
            if corner(a, b) not in g:
                g.add_node(corner(a, b), x=a * self.spacing, y=b * self.spacing)
        added = 0
        for (a0, b0), (a1, b1) in (((i, j), (i + 1, j)), ((i, j + 1), (i + 1, j + 1)), ((i, j), (i, j + 1)), ((i + 1, j), (i + 1, j + 1))):
            if not g.has_edge(corner(a0, b0), corner(a1, b1)):
                g.add_edge(corner(a0, b0), corner(a1, b1), length=self.spacing)
                added += 1
        return added

    def lots(self, i: int, j: int) -> list[tuple[float, float, float, float]]:
        """The four quarter lots of a block, as x, y, w, h."""
        sp = self.spacing
        out = []
        for qx, qy, qw, qh in QUADS:
            x = i * sp + 18 + qx * (sp - 36)
            y = j * sp + 18 + qy * (sp - 36)
            out.append((x, y, qw * (sp - 36) - 8, qh * (sp - 36) - 8))
        return out


@dataclass
class Plot:
    """An empty lot that Town Planning has zoned, waiting for a builder."""

    block: tuple[int, int]
    x: float
    y: float
    w: float
    h: float
    zone: str  # residential | commercial | industrial
    district: str

    def to_dict(self) -> dict:
        return {"x": round(self.x, 1), "y": round(self.y, 1), "w": round(self.w, 1), "h": round(self.h, 1), "zone": self.zone,
                "district": self.district}


def generate_city(seed: int, n: int = 16, spacing: float = 260.0, developed_radius: float = 5.6) -> City:
    """Build a city on an ``n`` x ``n`` grid of street corners."""
    rng = np.random.default_rng(seed)
    blocks = n - 1
    c = (blocks - 1) / 2.0

    def block_info(i: int, j: int) -> tuple[float, float]:
        dx, dy = i - c, j - c
        return math.hypot(dx, dy), math.atan2(dy, dx)

    developed = np.zeros((blocks, blocks), dtype=bool)
    for i in range(blocks):
        for j in range(blocks):
            r, _ = block_info(i, j)
            developed[i, j] = r + rng.normal(0, 0.35) <= developed_radius

    g = nx.Graph()
    node_id = lambda i, j: i * n + j  # noqa: E731
    for i in range(n):
        for j in range(n):
            g.add_node(node_id(i, j), x=i * spacing, y=j * spacing)

    def touches_developed(i0: int, j0: int, i1: int, j1: int) -> bool:
        cells = []
        if i0 == i1:  # vertical street between columns i0-1 and i0
            cells = [(i0 - 1, min(j0, j1)), (i0, min(j0, j1))]
        else:
            cells = [(min(i0, i1), j0 - 1), (min(i0, i1), j0)]
        return any(0 <= a < blocks and 0 <= b < blocks and developed[a, b] for a, b in cells)

    for i in range(n):
        for j in range(n):
            for di, dj in ((1, 0), (0, 1)):
                i1, j1 = i + di, j + dj
                if i1 < n and j1 < n and touches_developed(i, j, i1, j1):
                    g.add_edge(node_id(i, j), node_id(i1, j1), length=spacing)
    g.remove_nodes_from([v for v in list(g.nodes) if g.degree(v) == 0])

    # thin the grid a little, never disconnecting it and never leaving a dead corner
    for a, b in sorted(g.edges(), key=lambda e: rng.random()):
        if rng.random() < 0.09 and g.degree(a) > 2 and g.degree(b) > 2:
            g.remove_edge(a, b)
            if not nx.is_connected(g):
                g.add_edge(a, b, length=spacing)

    zones = _zone_blocks(rng, developed, c)
    zone_of: dict[tuple[int, int], str] = {}
    buildings: list[Building] = []
    counters: dict[str, int] = {}
    used: set[str] = set()
    for (i, j), zone in zones.items():
        zone_of[(i, j)] = "industrial" if zone == "industrial" else "commercial" if zone in ("downtown", "local", "civic") else "residential"
        r, ang = block_info(i, j)
        district = CENTRE if r < 1.8 else DISTRICTS[int(((ang + math.pi) / (2 * math.pi)) * 8) % 8]
        for kind, (qx, qy, qw, qh), extra in _block_layout(rng, zone, r):
            x = i * spacing + 18 + qx * (spacing - 36)
            y = j * spacing + 18 + qy * (spacing - 36)
            w, h = qw * (spacing - 36) - 8, qh * (spacing - 36) - 8
            node = _nearest_node(g, x + w / 2, y + h / 2)
            counters[kind] = counters.get(kind, 0) + 1
            name = _name(kind, district, counters[kind], extra, zone)
            base, k = name, 2
            head, _, tail = base.partition(", ")
            while name in used:  # "Ganga Niwas 2, Phool Baug"
                name, k = f"{head} {k}" + (f", {tail}" if tail else ""), k + 1
            used.add(name)
            b = Building(
                id=len(buildings), kind=kind, name=name,
                x=x, y=y, w=w, h=h, node=node, district=district,
            )
            t = TYPES[kind]
            if kind == "home":
                b.households = extra
            if kind == "school":
                b.students = 320
            for k in range(t.jobs):
                b.jobs.append(t.shifts[k % len(t.shifts)])
            buildings.append(b)
    return City(size=(n - 1) * spacing, spacing=spacing, graph=g, buildings=buildings, developed=developed, n=n, zones=zone_of)


def _zone_blocks(rng: np.random.Generator, developed: np.ndarray, c: float) -> dict[tuple[int, int], str]:
    zones: dict[tuple[int, int], str] = {}
    cells = [(i, j) for i in range(developed.shape[0]) for j in range(developed.shape[1]) if developed[i, j]]
    for i, j in cells:
        r = math.hypot(i - c, j - c)
        ang = math.degrees(math.atan2(j - c, i - c))
        if r < 2.3:
            zones[(i, j)] = "downtown"
        elif r > 3.6 and -40 < ang < 20:
            zones[(i, j)] = "industrial"
        elif rng.random() < 0.08:
            zones[(i, j)] = "park"
        elif rng.random() < 0.12:
            zones[(i, j)] = "local"  # neighbourhood shops
        else:
            zones[(i, j)] = "residential"
    # one civic block at the centre, the central park (LotusLab's pond lives here) beside it
    central = sorted((k for k, v in zones.items() if v == "downtown"), key=lambda k: ((k[0] - c) ** 2 + (k[1] - c) ** 2, k))
    if len(central) >= 2:
        zones[central[0]] = "civic"
        zones[central[1]] = "central_park"
    # schools: one per ~10 residential blocks, spread out
    res = [k for k, v in zones.items() if v == "residential"]
    for k in [res[i] for i in rng.permutation(len(res))[: max(2, len(res) // 10)]]:
        zones[k] = "school"
    # places of worship on residential streets: temples spread across the city, a few
    # masjids, and one place for each smaller community
    res = [k for k, v in zones.items() if v == "residential"]
    places = ["temple"] * max(3, len(res) // 9) + ["mosque"] * max(2, len(res) // 30) + ["church", "gurudwara", "vihara", "derasar", "agiary"]
    for k, kind in zip([res[i] for i in rng.permutation(len(res))], places):
        zones[k] = "worship:" + kind
    return zones


Layout = list[tuple[str, tuple[float, float, float, float], int]]
QUADS = ((0.0, 0.0, 0.5, 0.5), (0.5, 0.0, 0.5, 0.5), (0.0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5))


def _block_layout(rng: np.random.Generator, zone: str, r: float) -> Layout:
    full = (0.0, 0.0, 1.0, 1.0)
    if zone == "civic":
        kinds = ["city_hall", "police", "bank", "hospital"]
        return [(k, q, 0) for k, q in zip(kinds, QUADS)]
    if zone == "central_park":
        return [("park", full, 0)]
    if zone == "park":
        return [("park", full, 0)]
    if zone == "school":
        return [("school", (0, 0, 1.0, 0.5), 0), ("home", QUADS[2], 6), ("home", QUADS[3], 6)]
    if zone == "industrial":
        out: Layout = [("factory", (0, 0, 1.0, 0.5), 0)]
        out.append(("bus_depot" if rng.random() < 0.15 else "factory", (0, 0.5, 1.0, 0.5), 0))
        return out
    if zone == "downtown":
        out = []
        for q in QUADS:
            u = rng.random()
            out.append(("office" if u < 0.45 else "shop" if u < 0.7 else "restaurant" if u < 0.85 else "home", q, 12))
        return out
    if zone.startswith("worship:"):
        per = 8 if r < 3.5 else 3
        return [(zone[8:], QUADS[0], 0)] + [("home", q, per) for q in QUADS[1:]]
    if zone == "local":
        return [("shop", QUADS[0], 0), ("restaurant", QUADS[1], 0), ("home", QUADS[2], 4), ("home", QUADS[3], 4)]
    # residential: apartments nearer the centre, houses further out
    per = 8 if r < 3.5 else 3
    return [("home", q, per) for q in QUADS]


def _nearest_node(g: nx.Graph, x: float, y: float) -> int:
    best, best_d = -1, math.inf
    for v, d in g.nodes(data=True):
        dd = (d["x"] - x) ** 2 + (d["y"] - y) ** 2
        if dd < best_d:
            best, best_d = v, dd
    return int(best)


SHOPS = ("Ganesh Kirana", "Laxmi General Store", "Noor Provision Store", "Sai Supermarket", "Mehta Traders", "Patil Stores",
         "Annapurna Mart", "Royal Bazaar", "Shree Medical", "Bombay Cloth House", "Fresh Fruits Corner", "Bharat Hardware")
RESTAURANTS = ("Shiv Sagar", "Hotel Swad", "Bawarchi", "Irani Cafe", "Udupi Bhavan", "Punjab Dhaba", "Misal House",
               "Vaishali", "Chaitanya Paratha", "Cafe Goodluck", "Kolhapuri Rassa", "Bhatkal Biryani")
FACTORIES = ("Textile Mill", "Auto Parts", "Steel Works", "Foods", "Pharma", "Engineering Works", "Paper Mill", "Electricals")
FACTORY_BRANDS = ("Sahyadri", "Deccan", "Indrayani", "Godavari", "Krishna", "Bhima", "Mula", "Kamal")
OFFICES = ("IT Park", "Business Centre", "Corporate Tower", "Trade Centre", "Tech Hub")
SCHOOLS = ("Saraswati Vidya Mandir", "New English School", "Modern High School", "Sant Dnyaneshwar Vidyalaya",
           "St. Joseph's School", "Anjuman Urdu High School", "Bal Shikshan Mandir", "Zilla Parishad School")
PARKS = ("Phule Udyan", "Tilak Baug", "Nana-Nani Park", "Ganesh Udyan", "Azad Maidan", "Hirvai Garden")
HOMES = ("Sai Krupa", "Shanti", "Gokul", "Anand", "Sukh Sagar", "Ganga", "Om", "Green Valley", "Noor", "Mount Carmel", "Sunshine",
         "Laxmi", "Vrindavan", "Kalpataru", "Swapnapurti", "Shubham", "Jamuna", "Panchavati", "Neelkanth", "Gulmohar")
WORSHIP = {
    "temple": ("Ganpati Mandir", "Hanuman Mandir", "Vitthal Mandir", "Shiv Mandir", "Ram Mandir", "Devi Mandir", "Dattatreya Mandir",
               "Sai Baba Mandir"),
    "mosque": ("Jama Masjid", "Noorani Masjid", "Madina Masjid", "Makka Masjid"),
    "church": ("St. Mary's Church",),
    "gurudwara": ("Gurudwara Singh Sabha",),
    "vihara": ("Siddhartha Buddha Vihar",),
    "derasar": ("Shri Mahavir Jain Derasar",),
    "agiary": ("Kamalnagar Agiary",),
}


def _name(kind: str, district: str, k: int, households: int = 0, zone: str = "") -> str:
    pick = lambda names: names[(k - 1) % len(names)]  # noqa: E731
    if kind == "city_hall":
        return f"{CITY_NAME} Municipal Corporation"
    if kind == "bank":
        return "City Bank"
    if kind == "bus_depot":
        return f"{CITY_NAME} Bus Depot"
    if kind == "hospital":
        return f"{CITY_NAME} Civil Hospital"
    if kind == "police":
        return f"{CENTRE} Police Station"
    if kind == "park" and zone == "central_park":
        return "Kamal Talav"  # the lotus lake
    if kind in WORSHIP:
        return f"{pick(WORSHIP[kind])}, {district}"
    if kind == "home":
        return f"{pick(HOMES)} {'Housing Society' if households > 3 else 'Niwas'}, {district}"
    if kind == "factory":
        return f"{FACTORY_BRANDS[(k - 1) % len(FACTORY_BRANDS)]} {FACTORIES[(3 * k + (k - 1) // len(FACTORY_BRANDS)) % len(FACTORIES)]}"
    if kind == "office":
        return f"{district} {pick(OFFICES)}"
    names = {"shop": SHOPS, "restaurant": RESTAURANTS, "school": SCHOOLS, "park": PARKS}[kind]
    return f"{pick(names)}, {district}"
