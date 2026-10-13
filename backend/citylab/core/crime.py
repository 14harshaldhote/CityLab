"""Crime and justice in Kamalnagar: petty theft, police patrols, CCTV and the District Court.

**Who is tempted.** Hard times, not who you are. A person's temptation grows when
they are out of work, in debt or nearly broke, and with an impatient, careless
temperament (low conscientiousness and agreeableness). Someone who has already
been convicted is a little more likely to try again. Nothing here looks at a
person's religion, community, name or neighbourhood, and there is a test for that.

**What happens.** Every half hour a tempted person may try something, if the
moment allows it: picking a pocket in a crowd or on a full bus, slipping something
out of a shop, or breaking into a home whose family is out. A police patrol nearby
usually puts them off, and sometimes catches them in the act.

**Evidence.** Victims usually report it. A CCTV camera that covers the spot is the
strongest evidence, then witnesses who saw it. Detectives at the police station
work their open cases every day; good evidence and a fully staffed station solve
cases faster, and cases go cold after three weeks.

**The court.** An arrest goes to the District Court, which hears a few cases each
weekday afternoon. The stronger the evidence, the more likely a guilty verdict. A
first petty offence means a fine and paying the victim back; burglary or a repeat
offence also means time in jail, and a long sentence can cost someone their job,
which makes hard times harder. That loop is what the city lets you watch.

**Patrols and cameras.** Patrol cars come from the officers on duty. They drive
between the places where crimes were recently reported (hot-spot policing) and
random rounds. Every week the police put a new camera on the corner with the most
reported crime, if the city can afford it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from .citygen import _nearest_node
from .clock import MINUTES_PER_DAY, SimTime
from .people import JAIL, TRAVEL, Person
from .routing import BUS, CAR, Trip

if TYPE_CHECKING:
    from .world import World

TICK = 30  # minutes between chances to offend
ATTEMPT = 0.025  # per tick, times temptation
PATROL_RANGE = 350.0  # metres: a patrol this close puts most people off
DETERRED = 0.65
CAUGHT_IN_THE_ACT = 0.5
CAMERA_RANGE = 130.0
CAMERA_COST = 25_000.0
STARTING_CAMERAS = 5
PATROL_FUEL_PER_DAY = 250.0
COLD_DAYS = 21
HEARINGS_PER_DAY = 3
HEARING_DELAY_DAYS = 3
JAIL_DAYS = {"pickpocket": 6, "shoplift": 4, "burglary": 18}
LOSE_JOB_DAYS = 14
LABEL = {"pickpocket": "pickpocketing", "shoplift": "shoplifting", "burglary": "burglary"}
KIND_INDEX = {"pickpocket": 0, "shoplift": 1, "burglary": 2}
CROWD = 6
WORSHIP_OR_LEISURE = ("park", "restaurant", "temple", "mosque", "church", "gurudwara", "vihara", "derasar", "agiary", "hospital")


def temptation(p: Person, balance: float, debt: float, t: int) -> float:
    """0..1: how tempted someone is to steal. Hard times and temperament only."""
    age = p.age(t)
    if age < 18 or age >= 70:
        return 0.0
    hard = 0.0
    if p.job is None and not p.retired and p.school is None:
        hard += 0.45
    if debt > 0:
        hard += min(0.35, debt / 6000.0)
    if balance < 200:
        hard += 0.3
    temper = 0.5 * (1 - p.conscientiousness) + 0.5 * (1 - p.agreeableness)
    m = min(1.0, hard) * temper**2 + 0.015 * temper**3  # a sliver of opportunism in anyone
    return min(1.0, m * (1.6 if p.record else 1.0))


@dataclass
class Case:
    id: int
    kind: str
    t: int
    x: float
    y: float
    place: str
    building: int | None
    victim: str  # account
    victim_id: int | None
    victim_name: str
    offender: int
    value: float
    evidence: float = 0.05
    cctv: bool = False
    witnesses: int = 0
    reported: bool = True
    status: str = "investigating"  # unreported | investigating | awaiting trial | convicted | acquitted | unsolved
    caught: bool = False
    hearing_day: int | None = None
    verdict: str = ""

    def view(self, w: World, reveal: bool) -> dict[str, Any]:
        off = w.people.get(self.offender)
        known = reveal or self.status in ("awaiting trial", "convicted", "acquitted")
        return {
            "id": self.id, "kind": LABEL[self.kind], "when": SimTime(self.t).label(), "day": self.t // MINUTES_PER_DAY,
            "place": self.place, "building": self.building, "victim": self.victim_name, "victim_id": self.victim_id,
            "value": round(self.value), "evidence": round(self.evidence, 2), "cctv": self.cctv, "witnesses": self.witnesses,
            "status": self.status, "caught_in_the_act": self.caught, "verdict": self.verdict,
            "hearing": SimTime(self.hearing_day * MINUTES_PER_DAY + 15 * 60).label() if self.hearing_day is not None else None,
            "suspect": {"id": off.id, "name": off.name} if known and off is not None else None,
        }


@dataclass
class Patrol:
    id: int
    trip: Trip | None = None
    node: int = 0


@dataclass
class Day:
    crimes: int = 0
    reported: int = 0
    deterred: int = 0
    arrests: int = 0
    convicted: int = 0
    acquitted: int = 0
    stolen: float = 0.0


class Crime:
    def __init__(self, world: World) -> None:
        self.w = world
        self.rng = world.streams("crime")
        self.cases: dict[int, Case] = {}
        self._case_id = 0
        self.tempted: list[tuple[int, float]] = []
        self.patrols: list[Patrol] = []
        self._patrol_id = 0
        self.cameras: list[int] = []
        self.court: list[int] = []  # case ids waiting for a hearing
        self.today = Day()
        self.history: list[dict[str, Any]] = []
        self.on_duty = 0
        city = world.city
        cx = cy = city.size / 2
        nodes = sorted(city.graph.nodes, key=lambda n: (math.dist(city.node_xy(n), (cx, cy)), n))
        for n in nodes:  # cameras on the busiest central junctions, spread apart
            if len(self.cameras) >= STARTING_CAMERAS:
                break
            if all(math.dist(city.node_xy(n), city.node_xy(m)) > 300 for m in self.cameras):
                self.cameras.append(n)

    # ---- places ------------------------------------------------------------------------

    def _station(self) -> int | None:
        return next((b.id for b in self.w.city.buildings if b.kind == "police" and b.status == "open"), None)

    def covered(self, x: float, y: float) -> int | None:
        city = self.w.city
        for n in self.cameras:
            if math.dist(city.node_xy(n), (x, y)) <= CAMERA_RANGE:
                return n
        return None

    def _corner_name(self, node: int) -> str:
        tr = self.w.transport
        stop = tr.stops.get(node)
        if stop is not None:
            return stop.name
        nbrs = sorted(self.w.city.graph.neighbors(node))
        return tr.street_place(node, nbrs[0]) if nbrs else "a street corner"

    # ---- the clock -------------------------------------------------------------------------

    def tick(self, t: int) -> None:
        mod = t % MINUTES_PER_DAY
        if t % 5 == 0:
            self._patrol(t)
        if t % TICK == 0:
            self._tempt(t)
        if mod == 11 * 60:
            self._investigate(t)
        if mod == 15 * 60 and not SimTime(t).is_weekend:
            self._hearings(t)

    def daily(self) -> dict[str, Any]:
        """Once a day: who is tempted, release prisoners, fuel and cameras; returns yesterday's figures."""
        w = self.w
        econ = w.economy
        t = w.t
        self.tempted = []
        for p in w.alive():
            acct = econ.person(p.id)
            m = temptation(p, econ.balance[acct], econ._debt(acct), t)
            if m > 0.003 and p.jailed_until <= t:
                self.tempted.append((p.id, m))
        if self.patrols:
            econ.transfer("city", "outside", PATROL_FUEL_PER_DAY * len(self.patrols), "police patrols")
        if SimTime(t).day % 7 == 0:
            self._plan_cameras()
        day = SimTime(t).day - 1
        row = {"crimes": self.today.crimes, "crimes_reported": self.today.reported, "deterred": self.today.deterred,
               "arrests": self.today.arrests, "convicted": self.today.convicted, "acquitted": self.today.acquitted,
               "stolen": round(self.today.stolen), "cameras": len(self.cameras),
               "in_jail": sum(1 for p in w.alive() if p.jailed_until > t)}
        self.history.append({"day": day, **row})
        self.history = self.history[-30:]
        self.today = Day()
        return row

    # ---- patrols -----------------------------------------------------------------------------

    def _patrol(self, t: int) -> None:
        w = self.w
        station = self._station()
        if station is None:
            self.patrols = []
            return
        if t % TICK == 0:
            self.on_duty = sum(1 for q in w.job_holders.get(station, []) if w.people[q].activity == 4 and w.people[q].place == station)
            want = max(2, min(8, self.on_duty // 2))
            while len(self.patrols) < want:
                self._patrol_id += 1
                self.patrols.append(Patrol(self._patrol_id, node=w.city.buildings[station].node))
            if len(self.patrols) > want:
                self.patrols = self.patrols[:want]  # the last cars head back and park
        for pa in self.patrols:
            if pa.trip is None or t >= pa.trip.arrive:
                self._new_round(pa, t)

    def _new_round(self, pa: Patrol, t: int) -> None:
        w = self.w
        city = w.city
        rng = self.rng
        start = pa.trip.points[-1] if pa.trip is not None else city.node_xy(pa.node)
        src = _nearest_node(city.graph, *start) if pa.trip is not None else pa.node
        hot = [c for c in self.cases.values() if c.reported and t - c.t < 14 * MINUTES_PER_DAY]
        if hot and rng.random() < 0.6:
            c = hot[int(rng.integers(len(hot)))]
            dst = _nearest_node(city.graph, c.x, c.y)
        else:
            nodes = sorted(city.graph.nodes)
            dst = nodes[int(rng.integers(len(nodes)))]
        if dst == src:
            pa.trip = Trip(depart=t, arrive=t + 10, points=[start, start], times=[float(t), t + 10.0], legs=[CAR], mode="car")
            pa.node = src
            return
        nodes, _ = w.router._path(src, dst)
        times = w.transport._drive(nodes, t, "car", record=False, pace=0.8)
        pts = [city.node_xy(n) for n in nodes]
        pa.trip = Trip(depart=t, arrive=max(t + 1, math.ceil(times[-1])), points=pts, times=times, legs=[CAR] * (len(pts) - 1), mode="car")
        pa.node = dst

    def patrol_near(self, x: float, y: float, t: int) -> float:
        best = math.inf
        for pa in self.patrols:
            if pa.trip is not None:
                best = min(best, math.dist(pa.trip.position(t), (x, y)))
        return best

    # ---- temptation and theft ------------------------------------------------------------

    def _tempt(self, t: int) -> None:
        w = self.w
        rng = self.rng
        if not self.tempted:
            return
        tries = [(pid, m) for pid, m in self.tempted if rng.random() < m * ATTEMPT]
        if not tries:
            return
        inside: dict[int, list[int]] = defaultdict(list)
        for p in w.alive():
            if p.place is not None:
                inside[p.place].append(p.id)
        for pid, _ in tries:
            p = w.people.get(pid)
            if p is None or not p.alive or p.jailed_until > t:
                continue
            self._attempt(p, t, inside)

    def _attempt(self, p: Person, t: int, inside: dict[int, list[int]]) -> None:
        w = self.w
        rng = self.rng
        econ = w.economy
        hour = SimTime(t).hour
        home = w.households[p.household].home
        if p.place is not None and p.place != home:
            b = w.city.buildings[p.place]
            crowd = [q for q in inside.get(b.id, []) if q != p.id]
            x, y = b.x + b.w / 2, b.y + b.h / 2
            if b.kind == "shop" and len(crowd) < CROWD:
                self._commit(p, "shoplift", t, x, y, b.name, b.id, econ.company(b.id), None, b.name, float(rng.uniform(150, 600)), crowd)
                return
            if len(crowd) >= CROWD and b.kind in (*WORSHIP_OR_LEISURE, "shop"):
                self._pickpocket(p, t, x, y, b.name, b.id, crowd)
            return
        if p.activity == TRAVEL and p.trip is not None and p.trip.leg(t) == BUS:
            run = p.trip.run[0]  # type: ignore[index]
            riders = [q.id for q in w.alive() if q.id != p.id and q.trip is not None and q.trip.mode == "bus" and q.trip.run is not None
                      and q.trip.run[0] is run and q.trip.leg(t) == BUS]
            if len(riders) >= 3:
                x, y = p.trip.position(t)
                self._pickpocket(p, t, x, y, f"bus {run.route.number}", None, riders)
            return
        # a break-in: late at night or in the working day, when homes stand empty
        if not (hour >= 23 or hour < 4 or 10 <= hour < 16):
            return
        here = w.position(p)
        best = None
        for b, hhs in w.occupancy.items():
            if b == home or not hhs:
                continue
            bb = w.city.buildings[b]
            d = math.dist((bb.x + bb.w / 2, bb.y + bb.h / 2), here)
            if d > 600 or best is not None and d >= best[0]:
                continue
            for hid in hhs:
                members = w.households[hid].members
                if members and all(w.people[q].place != b for q in members):
                    best = (d, b, hid)
                    break
        if best is None:
            return
        _, b, hid = best
        bb = w.city.buildings[b]
        payer = econ._richest_adult(w.households[hid].members)
        if payer is None:
            return
        cash = max(0.0, econ.balance[econ.person(payer)])
        value = min(cash * 0.25, float(rng.uniform(800, 4000)))
        if value < 100:
            return
        victim = w.people[payer]
        self._commit(p, "burglary", t, bb.x + bb.w / 2, bb.y + bb.h / 2, bb.name, b, econ.person(payer), payer,
                     f"the {victim.last} family", value, [])

    def _pickpocket(self, p: Person, t: int, x: float, y: float, place: str, building: int | None, crowd: list[int]) -> None:
        w = self.w
        econ = w.economy
        marks = [q for q in crowd if w.people[q].age(t) >= 18 and econ.balance[econ.person(q)] > 200]
        if not marks:
            return
        v = w.people[marks[int(self.rng.integers(len(marks)))]]
        value = min(econ.balance[econ.person(v.id)] * 0.3, float(self.rng.uniform(60, 400)))
        self._commit(p, "pickpocket", t, x, y, place, building, econ.person(v.id), v.id, v.name, value, [q for q in crowd if q != v.id])

    def _commit(self, p: Person, kind: str, t: int, x: float, y: float, place: str, building: int | None, victim: str,
                victim_id: int | None, victim_name: str, value: float, crowd: list[int]) -> None:
        w = self.w
        rng = self.rng
        near = self.patrol_near(x, y, t)
        if near < PATROL_RANGE and rng.random() < DETERRED:
            self.today.deterred += 1
            return
        self._case_id += 1
        c = Case(self._case_id, kind, t, x, y, place, building, victim, victim_id, victim_name, p.id, round(value, 2))
        self.cases[c.id] = c
        w.economy.transfer(victim, w.economy.person(p.id), value, "stolen")
        self.today.crimes += 1
        self.today.stolen += value
        what = {"pickpocket": f"{victim_name}'s wallet was picked", "shoplift": f"Goods worth ₹{value:,.0f} were stolen",
                "burglary": f"Thieves broke into the home of {victim_name}"}[kind]
        where = f"on {place}" if place.startswith("bus") else f"at {place}"
        if near < PATROL_RANGE and rng.random() < CAUGHT_IN_THE_ACT:
            c.caught = True
            c.evidence = 0.9
            self.today.reported += 1
            w.emit("crime", f"{what} {where}, but a police patrol caught {p.name} in the act.", (p.id,) + ((victim_id,) if victim_id is not None else ()),
                   building, crime=LABEL[kind], value=round(value))
            self._arrest(c, t)
            return
        cam = self.covered(x, y)
        night = SimTime(t).hour >= 21 or SimTime(t).hour < 6
        if cam is not None:
            c.cctv = True
            c.evidence += 0.35 if night else 0.5
        c.witnesses = sum(1 for _ in crowd[:12] if rng.random() < 0.25)
        if kind == "burglary" and rng.random() < 0.3:
            c.witnesses += 1  # a neighbour heard something
        c.evidence = min(0.95, c.evidence + 0.12 * min(3, c.witnesses))
        c.reported = rng.random() < {"pickpocket": 0.7, "shoplift": 0.8, "burglary": 0.95}[kind]
        if not c.reported:
            c.status = "unreported"
            return
        self.today.reported += 1
        seen = " A CCTV camera recorded it." if c.cctv else ""
        seen += f" {c.witnesses} {'person' if c.witnesses == 1 else 'people'} saw it." if c.witnesses else ""
        w.emit("crime", f"{what} {where}.{seen} The police are investigating.", ((victim_id,) if victim_id is not None else ()), building,
               crime=LABEL[kind], value=round(value), case=c.id)

    # ---- the police station -----------------------------------------------------------------

    def _investigate(self, t: int) -> None:
        w = self.w
        station = self._station()
        staff = len(w.job_holders.get(station, [])) if station is not None else 0
        power = min(1.2, staff / 20.0)
        for c in sorted(self.cases.values(), key=lambda c: c.id):
            if c.status != "investigating":
                continue
            age = (t - c.t) / MINUTES_PER_DAY
            if age > COLD_DAYS:
                c.status = "unsolved"
                continue
            if self.rng.random() < c.evidence * 0.35 * power * (1.0 if age < 7 else 0.5):
                self._arrest(c, t)

    def _arrest(self, c: Case, t: int) -> None:
        w = self.w
        p = w.people.get(c.offender)
        if p is None or not p.alive:
            c.status = "unsolved"
            return
        c.status = "awaiting trial"
        self.today.arrests += 1
        today = t // MINUTES_PER_DAY
        day = today + HEARING_DELAY_DAYS
        booked: dict[int, int] = defaultdict(int)
        for cid in self.court:
            booked[self.cases[cid].hearing_day or 0] += 1
        while (day + 3) % 7 >= 5 or booked[day] >= HEARINGS_PER_DAY:  # weekdays only, a few cases a day
            day += 1
        c.hearing_day = day
        self.court.append(c.id)
        if not c.caught:
            how = "CCTV footage" if c.cctv else "witnesses" if c.witnesses else "patient detective work"
            w.emit("arrest", f"Police arrested {p.name} for the {LABEL[c.kind]} at {c.place}, thanks to {how}. They are out on bail until "
                             f"their hearing on {SimTime(day * MINUTES_PER_DAY).label()[:10]}.", (p.id,), c.building, case=c.id)

    # ---- the District Court ---------------------------------------------------------------------

    def _hearings(self, t: int) -> None:
        w = self.w
        econ = w.economy
        today = t // MINUTES_PER_DAY
        heard = [cid for cid in self.court if (self.cases[cid].hearing_day or 0) <= today][:HEARINGS_PER_DAY]
        court = next((b.id for b in w.city.buildings if b.kind == "court" and b.status == "open"), None)
        for cid in heard:
            self.court.remove(cid)
            c = self.cases[cid]
            p = w.people.get(c.offender)
            if p is None or not p.alive:
                c.status, c.verdict = "unsolved", "The accused is no longer in the city."
                continue
            if self.rng.random() < min(0.97, 0.25 + 0.7 * c.evidence):
                c.status = "convicted"
                self.today.convicted += 1
                acct = econ.person(p.id)
                back = min(c.value, max(0.0, econ.balance[acct]))
                econ.transfer(acct, c.victim, back, "paid back to victims")
                fine = round(max(200.0, c.value * 0.5), -1)
                econ.transfer(acct, "city", fine, "court fines")
                days = JAIL_DAYS[c.kind] * (1 + p.record) if c.kind == "burglary" or p.record else 0
                days = min(days, 60)
                p.record += 1
                sentence = f"fined ₹{fine:,.0f}" + (f" and jailed for {days} days" if days else "") + f", and must pay back ₹{c.value:,.0f}"
                c.verdict = f"Guilty: {sentence}."
                w.emit("court", f"District Court: {p.name} was found guilty of {LABEL[c.kind]} at {c.place}, {sentence}.", (p.id,), court,
                       case=c.id, verdict="guilty")
                if days:
                    self.jail(p, days, t)
            else:
                c.status = "acquitted"
                self.today.acquitted += 1
                c.verdict = "Not guilty: the evidence was not strong enough."
                w.emit("court", f"District Court: {p.name} was acquitted of {LABEL[c.kind]} at {c.place} for lack of evidence.", (p.id,), court,
                       case=c.id, verdict="not guilty")

    def jail(self, p: Person, days: int, t: int) -> None:
        w = self.w
        station = self._station()
        p.jailed_until = t + days * MINUTES_PER_DAY
        if p.job is not None and days >= LOSE_JOB_DAYS:
            place = w.city.buildings[p.job.building].name
            w.fire(p)
            p.unemployed_since = t
            w.emit("laid_off", f"{p.name} lost their job at {place} while in jail.", (p.id,))
        p.trip = None
        p.pending = None
        p.activity = JAIL
        p.place = station if station is not None else w.households[p.household].home
        p.until = p.jailed_until
        w.schedule(p)

    # ---- cameras -------------------------------------------------------------------------------------

    def _plan_cameras(self) -> None:
        w = self.w
        econ = w.economy
        t = w.t
        if econ.balance["city"] < 120_000:
            return
        recent = [c for c in self.cases.values() if c.reported and t - c.t < 30 * MINUTES_PER_DAY and self.covered(c.x, c.y) is None]
        if len(recent) < 3:
            return
        city = w.city
        counts: dict[int, int] = defaultdict(int)
        for c in recent:
            for n in city.graph.nodes:
                if math.dist(city.node_xy(n), (c.x, c.y)) <= CAMERA_RANGE * 1.2:
                    counts[n] += 1
        if not counts:
            return
        n, k = max(sorted(counts.items()), key=lambda kv: kv[1])
        if k < 3:
            return
        econ.transfer("city", "outside", CAMERA_COST, "CCTV cameras")
        self.cameras.append(n)
        city.version += 1
        w.emit("cctv", f"Police installed a CCTV camera at {self._corner_name(n)} after {k} reported thefts nearby.", camera=n)

    # ---- views ------------------------------------------------------------------------------------

    def cameras_view(self) -> list[dict[str, Any]]:
        city = self.w.city
        return [{"node": n, "x": city.node_xy(n)[0], "y": city.node_xy(n)[1], "name": self._corner_name(n)} for n in self.cameras]

    def frame(self, t: int) -> dict[str, Any]:
        police = []
        for pa in self.patrols:
            if pa.trip is None:
                continue
            x, y = pa.trip.position(t)
            ahead = pa.trip.position(t + 1)
            police.append([pa.id, round(x, 1), round(y, 1), round(math.atan2(ahead[1] - y, ahead[0] - x), 3) if ahead != (x, y) else 0.0])
        recent = [[round(c.x, 1), round(c.y, 1), t - c.t, KIND_INDEX[c.kind], 1 if c.status in ("awaiting trial", "convicted") else 0]
                  for c in self.cases.values() if t - c.t <= 180 and c.status != "unreported"]
        return {"police": police, "crimes": recent}

    def view(self) -> dict[str, Any]:
        w = self.w
        t = w.t
        cases = sorted(self.cases.values(), key=lambda c: -c.id)
        known = [c for c in cases if c.status != "unreported"]
        last30 = [c for c in cases if t - c.t < 30 * MINUTES_PER_DAY]
        solved = sum(1 for c in last30 if c.status in ("awaiting trial", "convicted", "acquitted"))
        reported = sum(1 for c in last30 if c.reported)
        return {
            "today": {"crimes_reported": self.today.reported, "arrests": self.today.arrests, "deterred": self.today.deterred,
                      "convicted": self.today.convicted, "acquitted": self.today.acquitted},
            "month": {"crimes": len(last30), "reported": reported, "solved": solved,
                      "with_cctv": sum(1 for c in last30 if c.cctv and c.reported),
                      "solved_with_cctv": sum(1 for c in last30 if c.cctv and c.status in ("awaiting trial", "convicted", "acquitted")),
                      "stolen": round(sum(c.value for c in last30))},
            "police": {"on_duty": self.on_duty, "patrols": len(self.patrols), "cameras": len(self.cameras)},
            "cases": [c.view(w, reveal=False) for c in known[:25]],
            "court": [self.cases[cid].view(w, reveal=True) for cid in self.court],
            "verdicts": [c.view(w, reveal=True) for c in known if c.status in ("convicted", "acquitted")][:10],
            "in_jail": [{"id": p.id, "name": p.name, "until": SimTime(p.jailed_until).label()} for p in w.alive() if p.jailed_until > t],
            "cameras": self.cameras_view(),
            "history": self.history[-14:],
        }
