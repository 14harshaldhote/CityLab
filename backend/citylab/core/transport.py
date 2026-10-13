"""Getting around Kamalnagar: traffic on every street, city buses and autos.

**Traffic.** Every car, auto-rickshaw and bus that turns into a street is counted
in ten-minute slots. The more vehicles a street carries compared with what it can
take, the slower everyone on it goes (the BPR curve traffic engineers use):

    minutes on a street = minutes when empty x (1 + 0.6 x (vehicles / capacity)^4)

so a street is fine until it is nearly full and then jams quickly, which is why the
morning rush suddenly crawls. Streets that jam day after day get widened by Public
Works (see ``agencies.py``).

**Buses.** Kamalnagar Municipal Transport runs five routes across the city, with a
stop every other corner. Buses leave each end on a timetable (every 12 minutes in the
rush, every 20 in the day, every 30 early and late), and they get stuck in the same
traffic as everyone else. A rider walks to a stop, waits for the next bus with room,
rides, and walks the rest of the way. Fares are 10 rupees (half for seniors, free for
children under 12) and go to the city; the city pays for the diesel.

**Choosing how to go.** Short trips are walked and people with a car drive. Everyone
else weighs walking, the bus and an auto by time and money: minutes walking or
waiting feel longer than minutes riding (much longer in the rain), and a fare costs
more to someone who earns less. They pick with a little randomness, so a street
always has a mix.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import networkx as nx
import numpy as np

from .citygen import CENTRE, Building, _nearest_node
from .clock import MINUTES_PER_DAY, SimTime
from .routing import AUTO, BUS, CAR, WAIT, WALK, WALK_M_PER_MIN, Trip, _access

if TYPE_CHECKING:
    from .people import Person
    from .world import World

FREE_SPEED = 450.0  # metres per minute on an empty street (27 km/h)
SLOT = 10  # minutes per traffic slot
CAPACITY = 3.5  # vehicles a street takes per slot before it slows (a small city, so small streets)
WIDE = 1.8  # a widened street takes this much more
UNDER_WORKS = 0.6  # and this much less while it is being widened
ALPHA, BETA, MAX_SLOWDOWN = 0.6, 4, 6.0
PCU = {"car": 1.0, "auto": 0.7, "bus": 1.0}  # how much room each vehicle takes
BUS_PACE = 0.85  # buses are a bit slower than cars
DWELL = 0.5  # minutes at each stop
BUS_ROOM = 60
AUTO_BASE, AUTO_PER_KM = 25.0, 13.0  # minimum fare covers the first 1.5 km
PETROL_PER_KM = 5.0
DIESEL_PER_KM = 1.5  # per bus-kilometre, a small city fleet
WALK_ONLY = 900.0  # metres: always walked
CAR_MIN = 1200.0  # metres: worth taking the car
TO_STOP = 650.0  # metres people will walk to or from a bus stop
SERVICE = (5 * 60 + 30, 23 * 60)
JAMMED = 1.0  # vehicles / capacity at which a street counts as jammed

# grid corners each route passes through; the third is a ring around the centre
ROUTES = (
    ("1", ((2, 8), (5, 8), (8, 8), (11, 8), (13, 8)), "#d2463c"),
    ("2", ((7, 2), (7, 5), (7, 8), (7, 11), (7, 13)), "#2c7fb8"),
    ("3", ((4, 4), (11, 4), (11, 11), (4, 11), (4, 4)), "#2f9a52"),
    ("4", ((3, 3), (5, 5), (8, 8), (10, 10), (12, 12)), "#e09a1b"),
    ("5", ((12, 3), (10, 5), (8, 7), (5, 10), (3, 12)), "#8a4fc6"),
)
# east-west streets by row, north-south streets by column
ROADS = ("Nadi Road", "Karve Road", "Tilak Road", "Laxmi Road", "Bajirao Road", "Shivaji Road", "Jangli Maharaj Road", "M.G. Road",
         "Station Road", "Nehru Road", "Sinhagad Road", "Satara Road", "Paud Road", "Nagar Road", "Solapur Road", "Kalwa Road")
MARGS = ("Ambedkar Marg", "Gokhale Marg", "Phule Marg", "Savarkar Marg", "Rani Laxmibai Marg", "Netaji Marg", "Sardar Patel Marg",
         "Gandhi Marg", "Azad Marg", "Tagore Marg", "Kasturba Marg", "Bhagat Singh Marg", "Shahu Marg", "Ahilyabai Marg",
         "Sane Guruji Marg", "Kabir Marg")
LANDMARKS = ("city_hall", "hospital", "police", "bank", "school", "park", "temple", "mosque", "church", "gurudwara", "vihara",
             "derasar", "agiary", "bus_depot")
CORNER_WORDS = ("Chowk", "Naka", "Phata", "Corner", "Gate", "Bus Stand", "Market", "Square")


def headway(minute_of_day: int) -> int:
    h = minute_of_day // 60
    if 7 <= h < 10 or 17 <= h < 20:
        return 12
    if 10 <= h < 17:
        return 20
    return 30


@dataclass
class Stop:
    id: int
    node: int
    name: str
    x: float
    y: float
    lines: list[str] = field(default_factory=list)


@dataclass
class Route:
    """One direction of one bus line."""

    index: int  # position in Transport.routes
    number: str
    name: str
    color: str
    nodes: list[int]
    xy: list[tuple[float, float]]
    stops: list[int]  # indexes into nodes where the bus stops
    towards: str  # name of the last stop
    departures: list[int] = field(default_factory=list)  # minute of day


@dataclass
class Run:
    id: int
    route: Route
    depart: int
    times: list[float]  # when the bus leaves each node
    load: list[int]  # riders on each segment
    riders: int = 0


@dataclass
class Today:
    trips: dict[str, int] = field(default_factory=lambda: {"walk": 0, "car": 0, "bus": 0, "auto": 0})
    commute_minutes: float = 0.0
    commutes: int = 0
    late: int = 0
    fares: float = 0.0
    bus_km: float = 0.0
    worst: tuple[float, tuple[int, int], int] | None = None  # ratio, street, minute
    rush_late: int = 0


class Transport:
    def __init__(self, world: World) -> None:
        self.w = world
        self.rng = world.streams("transport")
        self.load: dict[tuple[int, int], dict[int, float]] = defaultdict(dict)
        self.touched: dict[int, set[tuple[int, int]]] = defaultdict(set)
        self.peak: dict[tuple[int, int], float] = {}  # today's worst ratio per street
        self.rush_peak: dict[tuple[int, int], float] = {}  # the same, since the last rush-hour report
        self.jam_days: dict[tuple[int, int], list[int]] = {}  # days each street jammed
        self.stops: dict[int, Stop] = {}
        self.routes: list[Route] = []
        self.runs: dict[tuple[int, int], Run] = {}
        self._run_id = 0
        self._near: dict[int, list[tuple[int, int, float]]] = {}
        self._clock: list[tuple[int, int]] = []  # (minute of day, route) for every departure
        self._next = 0
        self.today = Today()
        self.riders_today: dict[str, int] = defaultdict(int)
        self.history: list[dict[str, Any]] = []
        self.last_bus_km = 0.0
        self._build_network()

    # ---- the network ------------------------------------------------------------------

    def _build_network(self) -> None:
        city = self.w.city
        g = city.graph
        sp = city.spacing
        used: set[str] = set()
        for number, corners, color in ROUTES:
            way = [_nearest_node(g, i * sp, j * sp) for i, j in corners]
            nodes = [way[0]]
            for a, b in zip(way, way[1:]):
                if a != b:
                    nodes += nx.shortest_path(g, a, b, weight="length")[1:]
            loop = nodes[0] == nodes[-1]
            stops_idx = sorted(set(range(0, len(nodes) - 1, 2)) | {len(nodes) - 1})
            for k in stops_idx:
                if nodes[k] not in self.stops:
                    x, y = city.node_xy(nodes[k])
                    self.stops[nodes[k]] = Stop(len(self.stops), nodes[k], self._stop_name(nodes[k], used), x, y)
                if number not in self.stops[nodes[k]].lines:
                    self.stops[nodes[k]].lines.append(number)
            first, last = self.stops[nodes[0]].name, self.stops[nodes[-1]].name
            if loop:
                name = f"Ring route around {CENTRE}"
                ends = (f"{CENTRE} ring, clockwise", f"{CENTRE} ring, anticlockwise")
            else:
                name = f"{first} to {last}"
                ends = (last, first)
            for d, (seq, towards) in enumerate(((nodes, ends[0]), (nodes[::-1], ends[1]))):
                n = len(seq)
                idx = stops_idx if d == 0 else sorted(n - 1 - k for k in stops_idx)
                r = Route(len(self.routes), number, name, color, list(seq), [city.node_xy(v) for v in seq], idx, towards)
                start = SERVICE[0] + d * 6 + int(number) * 3
                m = start
                while m <= SERVICE[1]:
                    r.departures.append(m)
                    m += headway(m)
                self.routes.append(r)
        self._clock = sorted((m, r.index) for r in self.routes for m in r.departures)

    def _stop_name(self, node: int, used: set[str]) -> str:
        city = self.w.city
        x, y = city.node_xy(node)
        i, j = round(x / city.spacing), round(y / city.spacing)
        district = city.district_at(i - 0.5, j - 0.5)
        best: tuple[float, str] | None = None
        for b in city.buildings:
            if b.kind in LANDMARKS:
                d = math.hypot(b.x + b.w / 2 - x, b.y + b.h / 2 - y)
                if d < 190 and (best is None or d < best[0]):
                    best = (d, b.name.split(", ")[0])
        names = ([best[1]] if best else []) + [f"{district} {w}" for w in CORNER_WORDS]
        if district == CENTRE:
            names.insert(0, CENTRE)
        for name in names:
            if name not in used:
                used.add(name)
                return name
        k = 2
        while f"{district} {k}" in used:
            k += 1
        used.add(f"{district} {k}")
        return f"{district} {k}"

    def street_name(self, a: int, b: int) -> str:
        city = self.w.city
        (x0, y0), (x1, y1) = city.node_xy(a), city.node_xy(b)
        if abs(y0 - y1) < 1:
            return ROADS[round(y0 / city.spacing) % len(ROADS)]
        return MARGS[round(x0 / city.spacing) % len(MARGS)]

    def street_place(self, a: int, b: int) -> str:
        city = self.w.city
        (x0, y0), (x1, y1) = city.node_xy(a), city.node_xy(b)
        district = city.district_at((x0 + x1) / 2 / city.spacing - 0.5, (y0 + y1) / 2 / city.spacing - 0.5)
        return f"{self.street_name(a, b)} in {district}"

    # ---- traffic ----------------------------------------------------------------------

    def capacity(self, e: tuple[int, int]) -> float:
        g = self.w.city.graph
        if not g.has_edge(*e):
            return CAPACITY
        d = g.edges[e]
        return CAPACITY * (WIDE if d.get("lanes", 1) > 1 else 1.0) * (UNDER_WORKS if d.get("works") else 1.0)

    def volume(self, e: tuple[int, int], t: float) -> float:
        """Vehicles per ten minutes, averaged over this slot and the one before."""
        s = int(t // SLOT)
        slots = self.load.get(e)
        if not slots:
            return 0.0
        return (slots.get(s, 0.0) + slots.get(s - 1, 0.0)) / 2.0

    def ratio(self, e: tuple[int, int], t: float) -> float:
        return self.volume(e, t) / self.capacity(e)

    def _drive(self, nodes: tuple[int, ...] | list[int], t0: float, kind: str, record: bool, pace: float = 1.0) -> list[float]:
        """Minute at which a vehicle reaches each node, in today's traffic."""
        g = self.w.city.graph
        times = [t0]
        t = t0
        for a, b in zip(nodes, nodes[1:]):
            e = (a, b) if a < b else (b, a)
            if record:
                s = int(t // SLOT)
                slots = self.load[e]
                slots[s] = slots.get(s, 0.0) + PCU[kind]
                self.touched[s].add(e)
            r = self.ratio(e, t)
            if record and r > self.rush_peak.get(e, 0.0):
                self.rush_peak[e] = r
            if record and r > self.peak.get(e, 0.0):
                self.peak[e] = r
                if self.today.worst is None or r > self.today.worst[0]:
                    self.today.worst = (r, e, int(t))
            slow = min(MAX_SLOWDOWN, 1.0 + ALPHA * r**BETA)
            length = g.edges[a, b]["length"] if g.has_edge(a, b) else math.dist(self.w.city.node_xy(a), self.w.city.node_xy(b))
            t += length / (FREE_SPEED * pace) * slow
            times.append(t)
        return times

    # ---- buses ------------------------------------------------------------------------

    def _run(self, r: Route, depart: int) -> Run:
        key = (r.index, depart)
        run = self.runs.get(key)
        if run is None:
            times = self._drive(r.nodes, depart, "bus", True, BUS_PACE)
            stops = set(r.stops)
            extra = 0.0
            for k in range(1, len(times)):  # a short wait at every stop on the way
                times[k] += extra
                if k in stops:
                    extra += DWELL
            self._run_id += 1
            run = Run(self._run_id, r, depart, times, [0] * (len(r.nodes) - 1))
            self.runs[key] = run
            km = sum(math.dist(p, q) for p, q in zip(r.xy, r.xy[1:])) / 1000.0
            self.today.bus_km += km
            self.w.economy.transfer("city", "outside", km * DIESEL_PER_KM, "bus diesel")
        return run

    def tick(self, t: int) -> None:
        """Buses leave on time, whether or not anyone has asked for them yet."""
        mod = t % MINUTES_PER_DAY
        if mod == 0:
            self._next = 0
        clock = self._clock
        while self._next < len(clock) and clock[self._next][0] <= mod:
            m, ri = clock[self._next]
            if m == mod:
                self._run(self.routes[ri], t)
            self._next += 1
        if mod % 60 == 0:
            self.runs = {k: r for k, r in self.runs.items() if r.times[-1] >= t - 5}
        if mod in (10 * 60, 20 * 60):
            self._rush_report(t, "Morning" if mod < 12 * 60 else "Evening")

    def _near_stops(self, b: Building) -> list[tuple[int, int, float]]:
        """(route, node index, walking metres) for every stop within reach of a building."""
        hit = self._near.get(b.id)
        if hit is None:
            cx, cy = b.x + b.w / 2, b.y + b.h / 2
            hit = []
            for r in self.routes:
                for k in r.stops:
                    x, y = r.xy[k]
                    d = abs(x - cx) + abs(y - cy)
                    if d <= TO_STOP:
                        hit.append((r.index, k, d))
            self._near[b.id] = hit
        return hit

    def _bus(self, p: Person, src: Building, dst: Building, t: int) -> tuple[Trip, float, float, float] | None:
        """The best single-bus journey, if there is one: (trip, walking, waiting, riding minutes)."""
        a = self._near_stops(src)
        b = self._near_stops(dst)
        if not a or not b:
            return None
        best = None
        for ra, ka, da in a:
            for rb, kb, db in b:
                if ra != rb or kb <= ka:
                    continue
                est = (da + db) / WALK_M_PER_MIN * 1.5 + (kb - ka) * 0.9
                if best is None or est < best[0]:
                    best = (est, ra, ka, kb)
        if best is None:
            return None
        _, ri, ka, kb = best
        r = self.routes[ri]
        w = self.w
        board_node, alight_node = r.nodes[ka], r.nodes[kb]
        walk1, _ = w.router._path(src.node, board_node)
        walk2, _ = w.router._path(alight_node, dst.node)
        pts = [(src.x + src.w / 2, src.y + src.h / 2)] + [w.city.node_xy(n) for n in walk1]
        times = [float(t)]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            times.append(times[-1] + math.hypot(x1 - x0, y1 - y0) / WALK_M_PER_MIN)
        legs = [WALK] * (len(pts) - 1)
        at_stop = times[-1]
        run = self._catch(r, ka, kb, at_stop, t)
        if run is None:
            return None
        walked = at_stop - t
        # wait at the stop, then ride
        pts.append(r.xy[ka])
        times.append(run.times[ka])
        legs.append(WAIT)
        for k in range(ka + 1, kb + 1):
            pts.append(r.xy[k])
            times.append(run.times[k])
            legs.append(BUS)
        ride = run.times[kb] - run.times[ka]
        wait = run.times[ka] - at_stop
        tail = [w.city.node_xy(n) for n in walk2[1:]] + [(dst.x + dst.w / 2, dst.y + dst.h / 2)]
        for x1, y1 in tail:
            x0, y0 = pts[-1]
            pts.append((x1, y1))
            times.append(times[-1] + math.hypot(x1 - x0, y1 - y0) / WALK_M_PER_MIN)
            legs.append(WALK)
        walked += times[-1] - run.times[kb]
        trip = Trip(depart=t, arrive=max(t + 1, math.ceil(times[-1])), points=pts, times=times, legs=legs, mode="bus", line=r.number,
                    run=(run, ka, kb), stop=self.stops[board_node].name)
        return trip, walked, wait, ride

    def _catch(self, r: Route, ka: int, kb: int, at_stop: float, t: int) -> Run | None:
        """The first bus on this route that reaches the stop after the rider and has room."""
        day = int(at_stop // MINUTES_PER_DAY)
        lead = ka * 2.0  # rough minutes from the start of the route to this stop
        tried = 0
        for d in (day, day + 1):
            for m in r.departures:
                dep = d * MINUTES_PER_DAY + m
                if dep + lead + 30 < at_stop:
                    continue
                if dep > at_stop + 90:
                    return None
                run = self._run(r, dep)
                tried += 1
                if run.times[ka] >= at_stop and max(run.load[ka:kb]) < BUS_ROOM:
                    return run
                if tried > 12:
                    return None
        return None

    # ---- choosing how to go -------------------------------------------------------------

    def plan(self, p: Person, src: Building, dst: Building, t: int, purpose: int | None = None) -> Trip:
        w = self.w
        pts, nodes = w.router.points(src, dst)
        dist = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        age = p.age(t)
        hh = w.households[p.household]
        if src.id == dst.id or dist < WALK_ONLY or age < 6:
            trip = self._walk(pts, t)
        elif hh.has_car and age >= 18 and dist >= CAR_MIN:
            trip = self._vehicle(pts, nodes, t, "car", record=True)
            self._pay(p, trip, dist)
        else:
            trip = self._choose(p, src, dst, pts, nodes, dist, t, age)
        self.today.trips[trip.mode] += 1
        if purpose is not None:
            self.today.commute_minutes += trip.arrive - t
            self.today.commutes += 1
        return trip

    def _walk(self, pts: list[tuple[float, float]], t: int) -> Trip:
        times = [float(t)]
        for a, b in zip(pts, pts[1:]):
            times.append(times[-1] + math.dist(a, b) / WALK_M_PER_MIN)
        return Trip(depart=t, arrive=max(t + 1, math.ceil(times[-1])), points=pts, times=times, legs=[WALK] * (len(pts) - 1), mode="walk")

    def _vehicle(self, pts: list[tuple[float, float]], nodes: tuple[int, ...], t: int, kind: str, record: bool) -> Trip:
        """Car or auto: get going (find the car, or hail an auto), drive in traffic, park."""
        start = 2.0 if kind == "car" else 3.0
        node_times = self._drive(nodes, t + start + math.dist(pts[0], pts[1]) / FREE_SPEED, kind, record)
        times = [float(t), t + start] + node_times + [node_times[-1] + math.dist(pts[-2], pts[-1]) / FREE_SPEED]
        points = [pts[0], pts[0]] + pts[1:]
        move = CAR if kind == "car" else AUTO
        legs = [WAIT if kind == "auto" else move] + [move] * (len(points) - 2)
        if kind == "car":  # parking
            times.append(times[-1] + 2)
            points.append(points[-1])
            legs.append(CAR)
        return Trip(depart=t, arrive=max(t + 1, math.ceil(times[-1])), points=points, times=times, legs=legs, mode=kind)

    def _value_of_time(self, p: Person, age: float) -> float:
        """Rupees a minute feels worth: what they earn, roughly."""
        if p.job is not None:
            return max(0.4, p.job.wage / 150.0)
        if age < 18:
            return 0.25
        return 0.5

    def _choose(self, p: Person, src: Building, dst: Building, pts, nodes, dist: float, t: int, age: float) -> Trip:
        w = self.w
        econ = w.economy
        rain = w.weather.at(t).raining
        effort = 1.5 * (1.8 if rain else 1.0) * (1.3 if age >= 65 else 1.0)
        vot = self._value_of_time(p, age)
        walk = self._walk(pts, t)
        walk_min = walk.arrive - t
        options: list[tuple[float, Trip]] = [(effort * walk_min + 0.04 * max(0.0, walk_min - 20) ** 2, walk)]
        payer = self._payer(p, age)
        bus = self._bus(p, src, dst, t)
        if bus is not None:
            trip, walked, wait, ride = bus
            fare = w.policy.bus_fare
            trip.fare = 0.0 if age < 12 else fare / 2 if age >= 65 else fare
            if trip.fare == 0 or payer is not None and econ.can_afford(payer, trip.fare):
                options.append((effort * walked + 1.4 * wait + ride + trip.fare / vot, trip))
        if age >= 16 and payer is not None:
            fare = round(AUTO_BASE + AUTO_PER_KM * max(0.0, dist / 1000.0 - 1.5), 0)
            if econ.can_afford(payer, fare + 100):
                auto = self._vehicle(pts, nodes, t, "auto", record=False)
                auto.fare = fare
                options.append(((auto.arrive - t) + fare / vot, auto))
        costs = np.array([c for c, _ in options])
        weights = np.exp(-(costs - costs.min()) / 6.0)
        pick = options[int(self.rng.choice(len(options), p=weights / weights.sum()))][1]
        if pick.mode == "auto":
            fare = pick.fare
            pick = self._vehicle(pts, nodes, t, "auto", record=True)
            pick.fare = fare
        if pick.mode == "bus":
            run, k0, k1 = pick.run  # type: ignore[misc]
            for k in range(k0, k1):
                run.load[k] += 1
            run.riders += 1
            self.riders_today[run.route.number] += 1
        if pick.mode in ("bus", "auto"):
            self._pay(p, pick, dist)
        return pick

    def _payer(self, p: Person, age: float) -> Person | None:
        if age >= 18:
            return p
        econ = self.w.economy
        q = econ._richest_adult(self.w.households[p.household].members)
        return self.w.people[q] if q is not None and self.w.people[q].age(self.w.t) >= 18 else None

    def _pay(self, p: Person, trip: Trip, dist: float) -> None:
        econ = self.w.economy
        payer = self._payer(p, p.age(self.w.t))
        if payer is None:
            return
        acct = econ.person(payer.id)
        if trip.mode == "car":
            econ.transfer(acct, "outside", PETROL_PER_KM * dist / 1000.0, "petrol")
        elif trip.mode == "bus" and trip.fare > 0:
            self.today.fares += econ.transfer(acct, "city", trip.fare, "bus fares")
        elif trip.mode == "auto":
            econ.transfer(acct, "outside", trip.fare, "auto fares")

    # ---- reports ------------------------------------------------------------------------

    def late_for_work(self) -> None:
        self.today.late += 1
        self.today.rush_late += 1

    def _rush_report(self, t: int, which: str) -> None:
        st = SimTime(t)
        if st.is_weekend:
            self.today.rush_late = 0
            return
        jams = self.jams(limit=1, peak=self.rush_peak)
        self.rush_peak = {}
        worst = f" The worst jam was on {jams[0]['street']}, down to {jams[0]['speed_kmh']} km/h." if jams else " Traffic kept moving."
        late = self.today.rush_late
        text = f"{which} rush hour is over.{worst} {late} {'person was' if late == 1 else 'people were'} late for work."
        self.w.emit("traffic", text, data={"late": late, "jam": jams[0] if jams else None})
        self.today.rush_late = 0

    def jams(self, limit: int = 6, peak: dict[tuple[int, int], float] | None = None) -> list[dict[str, Any]]:
        """The slowest streets right now (or each street at its worst in ``peak``)."""
        t = self.w.t
        cand: Any
        if peak is not None:
            cand = peak.items()
        else:
            s = int(t // SLOT)
            edges = self.touched.get(s, set()) | self.touched.get(s - 1, set())
            cand = ((e, self.ratio(e, self.w.t)) for e in edges)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for r, e in sorted(((r, e) for e, r in cand if r >= 0.5), key=lambda x: (-x[0], x[1])):
            street = self.street_place(*e)
            if street in seen:  # one line per street: its worst stretch
                continue
            seen.add(street)
            out.append({"street": street, "a": e[0], "b": e[1], "ratio": round(r, 2),
                        "speed_kmh": round(FREE_SPEED * 60 / 1000 / min(MAX_SLOWDOWN, 1 + ALPHA * r**BETA), 1)})
            if len(out) >= limit:
                break
        return out

    def close_day(self) -> dict[str, Any]:
        """Statistics for the day just ended; then start a fresh day."""
        w = self.w
        today = self.today
        day = SimTime(w.t).day - 1
        for e, r in self.peak.items():
            if r >= 1.3:
                self.jam_days.setdefault(e, []).append(day)
        for e in list(self.jam_days):
            self.jam_days[e] = [d for d in self.jam_days[e] if d > day - 7]
            if not self.jam_days[e]:
                del self.jam_days[e]
        riders = sum(self.riders_today.values())
        row = {
            "trips_walk": today.trips["walk"], "trips_car": today.trips["car"], "trips_bus": today.trips["bus"],
            "trips_auto": today.trips["auto"], "commute_min": round(today.commute_minutes / max(1, today.commutes), 1),
            "late": today.late, "bus_riders": riders, "bus_fares": round(today.fares, 2),
        }
        worst = self.jams(limit=1, peak=self.peak)
        row["worst_jam_kmh"] = worst[0]["speed_kmh"] if worst else None
        row["worst_jam"] = worst[0]["street"] if worst else None
        self.last_bus_km = today.bus_km
        if riders:
            busiest = max(sorted(self.riders_today), key=lambda k: self.riders_today[k])
            w.emit("buses", f"City buses carried {riders} passengers yesterday; route {busiest} was the busiest with "
                   f"{self.riders_today[busiest]}.", data={"riders": riders, "busiest": busiest})
        self.history.append({"day": day, **row})
        self.history = self.history[-30:]
        # forget old traffic
        s = int(w.t // SLOT)
        for e in list(self.load):
            slots = self.load[e]
            for k in [k for k in slots if k < s - 2]:
                del slots[k]
            if not slots:
                del self.load[e]
        for k in [k for k in self.touched if k < s - 2]:
            del self.touched[k]
        self.peak = {}
        self.today = Today()
        self.riders_today = defaultdict(int)
        return row

    # ---- views ---------------------------------------------------------------------------

    def network(self) -> dict[str, Any]:
        lines = []
        for r in self.routes[::2]:
            lines.append({"number": r.number, "name": r.name, "color": r.color, "nodes": r.nodes,
                          "stops": [self.stops[r.nodes[k]].id for k in r.stops]})
        stops = sorted(self.stops.values(), key=lambda s: s.id)
        return {"lines": lines, "stops": [{"id": s.id, "name": s.name, "x": s.x, "y": s.y, "node": s.node, "lines": s.lines} for s in stops]}

    def active(self, t: int) -> list[Run]:
        return [r for r in self.runs.values() if r.times[0] <= t <= r.times[-1]]

    def buses(self, t: int) -> list[list[float]]:
        """[id, x, y, heading, route index, riders] for every bus on the road."""
        out = []
        for run in self.active(t):
            r = run.route
            k = max(0, min(len(run.times) - 2, next((i for i in range(len(run.times) - 1) if run.times[i + 1] > t), len(run.times) - 2)))
            span = run.times[k + 1] - run.times[k]
            f = 0.0 if span <= 0 else min(1.0, max(0.0, (t - run.times[k]) / span))
            (x0, y0), (x1, y1) = r.xy[k], r.xy[k + 1]
            out.append([run.id, round(x0 + (x1 - x0) * f, 1), round(y0 + (y1 - y0) * f, 1), round(math.atan2(y1 - y0, x1 - x0), 3),
                        int(r.number), run.load[k]])
        return out

    def traffic(self, t: int) -> list[list[float]]:
        s = int(t // SLOT)
        edges = self.touched.get(s, set()) | self.touched.get(s - 1, set())
        out = []
        for e in sorted(edges):
            r = self.ratio(e, t)
            if r >= 0.3:
                out.append([e[0], e[1], round(r, 2)])
        return out

    def describe(self, p: Person, t: int) -> str | None:
        trip = p.trip
        if trip is None:
            return None
        leg = trip.leg(t)
        if trip.mode == "bus":
            if leg == WAIT:
                return f"Waiting for bus {trip.line} at {trip.stop}"
            if leg == BUS:
                return f"On bus {trip.line} towards {trip.run[0].route.towards}"  # type: ignore[index]
            return "Walking to the bus stop" if t < trip.times[next(i for i, l in enumerate(trip.legs) if l == WAIT)] else "Walking from the bus stop"
        if trip.mode == "auto":
            return "Hailing an auto-rickshaw" if leg == WAIT else "Riding in an auto-rickshaw"
        if trip.mode == "car":
            return "Driving"
        return "Walking"

    def view(self) -> dict[str, Any]:
        w = self.w
        t = w.t
        moving = defaultdict(int)
        for p in w.alive():
            if p.trip is not None and p.place is None:
                moving[p.trip.leg(t)] += 1
        active = self.active(t)
        lines = []
        for r in self.routes[::2]:
            both = [x for x in self.routes if x.number == r.number]
            lines.append({
                "number": r.number, "name": r.name, "color": r.color, "stops": len(r.stops),
                "km": round(sum(math.dist(a, b) for a, b in zip(r.xy, r.xy[1:])) / 1000.0, 1),
                "buses_now": sum(1 for run in active if run.route in both),
                "riders_now": sum(run.load[min(len(run.load) - 1, max(0, _seg(run.times, t)))] for run in active if run.route in both),
                "riders_today": self.riders_today.get(r.number, 0),
                "every": headway(t % MINUTES_PER_DAY) if SERVICE[0] <= t % MINUTES_PER_DAY <= SERVICE[1] else None,
            })
        g = w.city.graph
        return {
            "now": {"walking": moving[WALK], "driving": moving[CAR], "on_buses": moving[BUS], "in_autos": moving[AUTO],
                    "waiting": moving[WAIT], "buses": len(active)},
            "jams": self.jams(),
            "lines": lines,
            "today": {"trips": dict(self.today.trips), "commute_min": round(self.today.commute_minutes / max(1, self.today.commutes), 1),
                      "late": self.today.late, "fares": round(self.today.fares, 2), "bus_km": round(self.today.bus_km, 1)},
            "history": self.history[-14:],
            "fares": {"bus": self.w.policy.bus_fare, "auto_min": AUTO_BASE, "auto_per_km": AUTO_PER_KM, "petrol_per_km": PETROL_PER_KM},
            "widened": [self.street_place(a, b) for a, b in sorted(g.edges()) if g.edges[a, b].get("lanes", 1) > 1],
        }


def _seg(times: list[float], t: float) -> int:
    for i in range(len(times) - 1):
        if times[i + 1] > t:
            return i
    return len(times) - 2
