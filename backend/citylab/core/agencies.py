"""The people who run and build the city: government departments and private builders.

Once a day each department looks at the city and decides what it needs, the way a
real municipal corporation does, with plain rules that can be read and printed
(later, AI leaders can take over the same decisions):

* **Town Planning** watches homes, jobs, school seats and places of worship. When
  something is running out it zones land: first the empty lots it already has,
  and when those are gone a new block at the edge of the city, as close to the
  centre as possible so the city grows outwards in rings.
* **Public Works (PWD)** lays the streets for every new block (the street graph
  grows, so routing changes) and builds public buildings such as schools.
* **Education** asks for a new school when seats run short.
* **Water Supply** charges every household a small water bill and pays to pump it.
* **Municipal Transport** runs the city buses (see ``transport.py``), and when a
  street jams day after day, PWD widens it to four lanes.
* **Private builders** (developers, new companies and community trusts) take out a
  City Bank loan, hire a crew, and put up the building. A housing society is sold
  to the landlord when it is finished; a new company opens for business; a new
  mandir or masjid is handed to its community trust.

Construction is real work: the crew's shifts are jobs people can take, the building
rises day by day with the number who turn up (contract labour from outside fills
the gaps, at a cost), and the money moves through the same double-entry books as
everything else.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from .citygen import TYPES, Building, Plot, Shift, _name, _nearest_node
from .clock import MINUTES_PER_DAY, MINUTES_PER_HOUR as H
from .faith import FAITHS, PLACE_KINDS

if TYPE_CHECKING:
    from .world import World

SITE_SHIFT = Shift(8 * H, 17 * H, False)
SITE_WAGE = 115.0
CREW = {"home": 10, "office": 16, "factory": 14, "shop": 8, "restaurant": 6, "school": 12, "park": 4}
BUILD_DAYS = {"home": 45, "apartment": 80, "office": 110, "factory": 80, "shop": 35, "restaurant": 30, "school": 70, "park": 20}
MATERIALS_PER_DAY = {"home": 900.0, "apartment": 1800.0, "office": 2600.0, "factory": 2000.0, "shop": 700.0, "restaurant": 600.0,
                     "school": 1500.0, "park": 300.0}
ROAD_DAYS = 12
ROAD_COST_PER_DAY = 2500.0
WIDEN_DAYS = 8
WIDEN_COST_PER_DAY = 3000.0
JAM_DAYS_TO_WIDEN = 4  # out of the last seven
WATER_BILL = 2.0  # per person per day
WATER_COST_SHARE = 0.6  # of the bill spent pumping and treating it
SALE_MARGIN = 1.15  # a housing society sells for its cost plus this margin
DEVELOPERS = ("Sahyadri Developers", "Kalpataru Builders", "Gokul Constructions", "Noor Builders", "Mehta Realty", "Deccan Infra",
              "Pawar Housing", "Shubham Constructions")
PUBLIC_PROJECTS = ("school", "park")
PLAN_AHEAD_WEEKS = 52  # Town Planning keeps a year's worth of homes ready
PEOPLE_PER_SHOP = 48
# people per place of worship before a community asks for another one
WORSHIP_LOAD = {"temple": 450, "mosque": 300, "church": 250, "gurudwara": 250, "vihara": 250, "derasar": 250, "agiary": 250}


@dataclass
class Department:
    key: str
    name: str
    sector: str  # "government" | "private"
    does: str  # one line: what it is for
    watching: str = ""  # what it looked at today, in words
    head: int | None = None  # a City Hall employee, for government departments
    spent: float = 0.0
    done: int = 0


@dataclass
class Project:
    building: int
    kind: str  # what it will be (styleKind: "apartment" for big housing)
    owner: str  # who is building it
    account: str  # who pays the crew and materials
    started: int  # day
    days: int  # planned build time
    cost: float = 0.0
    why: str = ""


@dataclass
class Roadwork:
    block: tuple[int, int]
    zone: str
    started: int
    progress: float = 0.0
    why: str = ""


@dataclass
class Widening:
    edge: tuple[int, int]
    street: str
    started: int
    progress: float = 0.0
    why: str = ""


@dataclass
class Government:
    w: World
    departments: dict[str, Department] = field(default_factory=dict)
    projects: dict[int, Project] = field(default_factory=dict)
    roadworks: list[Roadwork] = field(default_factory=list)
    widening: list[Widening] = field(default_factory=list)
    finished: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for d in (
            Department("planning", "Town Planning Department", "government", "Zones land and decides where the city grows."),
            Department("pwd", "Public Works Department", "government", "Lays new streets and builds schools and parks."),
            Department("education", "Education Department", "government", "Makes sure every child has a school seat."),
            Department("water", "Water Supply Department", "government", "Supplies water to every home and bills for it."),
            Department("transport", "Kamalnagar Municipal Transport", "government", "Runs the city buses and keeps an eye on traffic."),
            Department("police", "Kamalnagar Police", "government", "Patrols the streets, investigates thefts and puts up CCTV cameras."),
            Department("court", "District Court", "government", "Hears the cases the police bring and decides who is guilty."),
            Department("health", "Kamalnagar Civil Hospital", "government", "Treats the sick, free for those who can't afford it."),
            Department("tax", "Municipal Tax Office", "government", "Collects taxes and audits businesses that dodge them."),
            Department("builders", "Private builders", "private", "Developers who build housing societies, offices and shops."),
            Department("trusts", "Community trusts", "private", "Raise money to build new places of worship."),
        ):
            self.departments[d.key] = d

    # ---- the daily round --------------------------------------------------------------

    def daily(self) -> None:
        w = self.w
        rng = w.streams("agencies")
        self._heads()
        self._water()
        self._transport()
        self._justice()
        self._health()
        self._tax(rng)
        self._build(rng)
        self._roads()
        self._widen()
        self._plan(rng)

    def _heads(self) -> None:
        """Each department is led by someone who works at the municipal corporation."""
        w = self.w
        home_of = {"police": "police", "court": "court", "health": "hospital"}  # led from their own building; the rest from City Hall
        taken = {d.head for d in self.departments.values() if d.head is not None}
        for d in self.departments.values():
            if d.sector != "government":
                continue
            kind = home_of.get(d.key, "city_hall")
            hall = next((b.id for b in w.city.buildings if b.kind == kind and b.status == "open"), None)
            staff = sorted(w.job_holders.get(hall, []), key=lambda q: (-w.people[q].skill, q)) if hall is not None else []
            p = w.people.get(d.head) if d.head is not None else None
            if p is None or not p.alive or p.job is None or p.job.building != hall:
                taken.discard(d.head)
                d.head = next((q for q in staff if q not in taken), None)
                if d.head is not None:
                    taken.add(d.head)

    def _water(self) -> None:
        econ = self.w.economy
        d = self.departments["water"]
        billed = 0.0
        families = 0
        for hh in self.w.households.values():
            if hh.members:
                econ._household_pays(hh.members, "city", WATER_BILL * len(hh.members), "water bills")
                billed += WATER_BILL * len(hh.members)
                families += 1
        cost = econ.transfer("city", "outside", billed * WATER_COST_SHARE, "water supply")
        d.spent += cost
        d.watching = f"Billed {families} families {billed:,.0f} for water today."

    def _transport(self) -> None:
        tr = self.w.transport
        d = self.departments["transport"]
        if not tr.history:
            return
        y = tr.history[-1]
        from .transport import DIESEL_PER_KM

        d.spent += tr.last_bus_km * DIESEL_PER_KM
        d.done = 0
        jam = f" Slowest street: {y['worst_jam']}." if y.get("worst_jam") else ""
        d.watching = (f"Buses carried {y['bus_riders']} passengers yesterday. The average trip to work or school took "
                      f"{y['commute_min']:.0f} minutes and {y['late']} people were late for work.{jam}")

    def _justice(self) -> None:
        cr = self.w.crime
        police, court = self.departments["police"], self.departments["court"]
        open_cases = sum(1 for c in cr.cases.values() if c.status == "investigating")
        police.watching = (f"{open_cases} open {'case' if open_cases == 1 else 'cases'}, {len(cr.patrols)} patrol "
                           f"{'car' if len(cr.patrols) == 1 else 'cars'} on the road and {len(cr.cameras)} CCTV cameras.")
        police.done = sum(1 for c in cr.cases.values() if c.status in ("awaiting trial", "convicted", "acquitted"))
        court.watching = f"{len(cr.court)} {'case' if len(cr.court) == 1 else 'cases'} waiting for a hearing."
        court.done = sum(1 for c in cr.cases.values() if c.status in ("convicted", "acquitted"))

    def _health(self) -> None:
        from .health import is_doctor

        w = self.w
        d = self.departments["health"]
        doctors = sum(1 for p in w.alive() if is_doctor(w, p))
        from .health import CHECKUP

        sick = sum(1 for p in w.alive() if p.illness not in (None, CHECKUP))
        today = w.health.today
        d.done += today["visits"]
        d.spent += w.economy.city_out.get("medicines", 0.0)
        d.watching = f"{doctors} doctors on the staff; {sick} people ill in the city; {today['visits']} patients seen today."

    def _tax(self, rng: np.random.Generator) -> None:
        w = self.w
        d = self.departments["tax"]
        econ = w.economy
        if (w.t // MINUTES_PER_DAY) % 7 == 3:  # audit day
            done = econ.audit(rng)
            caught = sum(1 for a in done if a["caught"])
            d.done += caught
            self.last_audit = f"This week it audited {len(done)} businesses and caught {caught} dodging tax."
        dodge = econ.dodging()
        d.watching = (f"{dodge['taxpayers']} people pay income tax; {dodge['cash_workers']} are paid cash in hand and "
                      f"{dodge['cash_books']} shops and restaurants under-declare their takings. " + getattr(self, "last_audit", ""))

    # ---- construction ---------------------------------------------------------------------

    def _build(self, rng: np.random.Generator) -> None:
        w = self.w
        econ = w.economy
        for bid in sorted(self.projects):
            pr = self.projects[bid]
            b = w.city.buildings[bid]
            crew = len(b.jobs)
            came = len(econ.attendance.get(bid, []))
            # contract labour from outside fills the gaps, so building never stops completely
            missing = max(0, crew - came)
            econ.transfer(pr.account, "outside", missing * SITE_WAGE * 0.5, "contract labour")
            econ.transfer(pr.account, "outside", MATERIALS_PER_DAY.get(pr.kind, 800.0) * (0.6 + 0.4 * came / max(1, crew)), "building materials")
            b.progress = min(1.0, b.progress + (0.8 + 0.2 * came / max(1, crew)) / pr.days)
            if b.progress >= 1.0:
                self._finish(pr, b)

    def _start(self, plot: Plot, kind: str, extra: int, owner: str, account_for: str, why: str, dept: str, style: str | None = None) -> Building:
        """Put up a construction site on a plot. ``account_for`` is "city", "loan" or an existing account."""
        w = self.w
        city = w.city
        econ = w.economy
        bid = len(city.buildings)
        counters = sum(1 for b in city.buildings if b.kind == kind) + 1
        name = _name(kind, plot.district, counters, extra, "")
        base, k = name, 2
        used = {b.name for b in city.buildings}
        head, _, tail = base.partition(", ")
        while name in used:
            name, k = f"{head} {k}" + (f", {tail}" if tail else ""), k + 1
        b = Building(id=bid, kind=kind, name=name, x=plot.x, y=plot.y, w=plot.w, h=plot.h,
                     node=_nearest_node(city.graph, plot.x + plot.w / 2, plot.y + plot.h / 2), district=plot.district,
                     status="construction", progress=0.0, owner=owner, households_planned=extra, zone=plot.zone)
        b.jobs = [SITE_SHIFT] * CREW.get(kind if kind in CREW else "home", 8)
        city.buildings.append(b)
        city.plots.remove(plot)
        city.version += 1
        w.job_holders[bid] = []
        style = style or ("apartment" if kind == "home" and extra > 3 else kind)
        days = BUILD_DAYS.get(style, 60)
        cost = days * (len(b.jobs) * SITE_WAGE + MATERIALS_PER_DAY.get(style, 800.0))
        if account_for == "city":
            account = "city"
        else:
            account = econ.company(bid)
            econ.credit[account] = 680.0
            econ._borrow(account, round(cost * 1.3, 2), f"to build {name}", days=3 * 365)
        if dept == "pwd":
            self.departments["pwd"].watching = f"Building {name}."
        pr = Project(bid, style, owner, account, w.t // MINUTES_PER_DAY, days, cost, why)
        self.projects[bid] = pr
        where = "" if plot.district in name else f" in {plot.district}"
        w.emit("construction", f"{owner} started building {name}{where}: {why}", place=bid,
               owner=owner, building_kind=kind, days=days, cost=round(cost))
        return b

    def _finish(self, pr: Project, b: Building) -> None:
        w = self.w
        econ = w.economy
        t = TYPES[b.kind]
        for pid in list(w.job_holders.get(b.id, [])):
            p = w.people[pid]
            w.fire(p)
            p.unemployed_since = w.t  # the crew moves on and looks for the next job
        b.status = "open"
        b.progress = 1.0
        b.opened_day = w.t // MINUTES_PER_DAY
        b.jobs = [t.shifts[k % len(t.shifts)] for k in range(t.jobs)] if t.jobs else []
        if b.kind == "home":
            b.households = b.households_planned
        if b.kind == "school":
            b.students = 320
        w.register(b)
        del self.projects[b.id]
        w.city.version += 1
        if b.kind == "home":
            # the landlord buys the finished building; the developer clears its loan and keeps the margin
            price = round(pr.cost * SALE_MARGIN, 2)
            if econ.balance["landlord"] < price:
                econ._borrow("landlord", price - econ.balance["landlord"] + 10_000.0, f"to buy {b.name}", days=5 * 365)
            econ.transfer("landlord", pr.account, price, "property sales")
            for loan in [l for l in econ.loans.values() if l.account == pr.account]:
                pay = min(max(0.0, econ.balance[pr.account]), loan.balance)
                econ.transfer(pr.account, "bank", pay, "loan repayments")
                loan.balance -= pay
                if loan.balance <= 0.01:
                    del econ.loans[loan.id]
            if econ.balance[pr.account] > 0:
                econ.transfer(pr.account, "outside", econ.balance[pr.account], "builders' profit")
        dept = "pwd" if pr.account == "city" else "trusts" if b.kind in PLACE_KINDS else "builders"
        self.departments[dept].done += 1
        self.finished.append({"building": b.id, "name": b.name, "kind": b.kind, "owner": pr.owner, "day": b.opened_day,
                              "district": b.district})
        what = f"{b.households} homes" if b.kind == "home" else f"{len(b.jobs)} jobs" if b.jobs else "open to all"
        where = "" if b.district in b.name else f" in {b.district}"
        w.emit("opened", f"{b.name} opened{where} ({what}), built by {pr.owner} in {b.opened_day - pr.started} days.",
               place=b.id, building_kind=b.kind)

    # ---- streets ------------------------------------------------------------------------------

    def _roads(self) -> None:
        w = self.w
        d = self.departments["pwd"]
        for rw in list(self.roadworks):
            d.spent += w.economy.transfer("city", "outside", ROAD_COST_PER_DAY, "road works")
            rw.progress += 1.0 / ROAD_DAYS
            if rw.progress >= 1.0:
                self.roadworks.remove(rw)
                self._open_block(rw)

    def _widen(self) -> None:
        """Streets that jam day after day get two more lanes. Traffic squeezes past the works meanwhile."""
        w = self.w
        g = w.city.graph
        econ = w.economy
        d = self.departments["pwd"]
        for wd in list(self.widening):
            d.spent += econ.transfer("city", "outside", WIDEN_COST_PER_DAY, "road widening")
            wd.progress += 1.0 / WIDEN_DAYS
            if wd.progress >= 1.0 - 1e-9:
                self.widening.remove(wd)
                if g.has_edge(*wd.edge):
                    g.edges[wd.edge]["lanes"] = 2
                    g.edges[wd.edge].pop("works", None)
                if wd.edge in w.city.widening:
                    w.city.widening.remove(wd.edge)
                w.city.version += 1
                d.done += 1
                w.emit("roads", f"{wd.street} now has four lanes. The Public Works Department finished widening it in {WIDEN_DAYS} days.")
        if self.widening or econ.balance["city"] < 150_000:
            return
        tr = w.transport
        jams = sorted((-len(days), e) for e, days in tr.jam_days.items()
                      if len(days) >= JAM_DAYS_TO_WIDEN and g.has_edge(*e) and g.edges[e].get("lanes", 1) == 1)
        if not jams:
            return
        n, e = -jams[0][0], jams[0][1]
        street = tr.street_place(*e)
        why = f"it jammed on {n} of the last 7 days"
        g.edges[e]["works"] = True
        w.city.widening.append(e)
        w.city.version += 1
        self.widening.append(Widening(e, street, w.t // MINUTES_PER_DAY, why=why))
        w.emit("roads", f"The Public Works Department started widening {street} because {why}. Expect delays.")

    def _open_block(self, rw: Roadwork) -> None:
        w = self.w
        city = w.city
        i, j = rw.block
        city.lay_streets(i, j)
        city.roadworks.remove(rw.block)
        city.zones[rw.block] = rw.zone
        for x, y, ww, hh in city.lots(i, j):
            city.plots.append(Plot(rw.block, x, y, ww, hh, rw.zone, city.district_at(i, j)))
        city.version += 1
        w.router.invalidate()
        self.departments["pwd"].done += 1
        w.emit("roads", f"The Public Works Department finished the streets around a new {rw.zone} block in {city.district_at(i, j)}; "
                        f"four plots are ready for building.", zone=rw.zone)

    def _new_block(self, rng: np.random.Generator, zone: str, why: str) -> bool:
        """Zone the empty block nearest the centre that touches the city, and ask PWD for its streets."""
        city = self.w.city
        if any(rw.zone == zone for rw in self.roadworks):
            return False
        c = (city.n - 2) / 2.0
        taken = set(city.zones) | {rw.block for rw in self.roadworks}
        options = []
        for i in range(city.n - 1):
            for j in range(city.n - 1):
                if (i, j) in taken:
                    continue
                if not any((i + di, j + dj) in city.zones for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    continue
                ang = math.degrees(math.atan2(j - c, i - c))
                east = -40 < ang < 20
                fit = 0.0 if (zone == "industrial") == east else 1.5  # factories go to the eastern mill side
                options.append((math.hypot(i - c, j - c) + fit + float(rng.uniform(0, 0.4)), i, j))
        if not options:
            return False
        _, i, j = min(options)
        rw = Roadwork((i, j), zone, self.w.t // MINUTES_PER_DAY, why=why)
        self.roadworks.append(rw)
        city.roadworks.append((i, j))
        city.version += 1
        district = city.district_at(i, j)
        self.w.emit("zoning", f"Town Planning zoned a new {zone} block in {district}: {why} "
                              f"The Public Works Department is laying its streets.", zone=zone, district=district)
        return True

    # ---- planning ---------------------------------------------------------------------------------

    def _plot(self, zone: str) -> Plot | None:
        c = (self.w.city.n - 2) / 2.0
        sp = self.w.city.spacing
        free = [p for p in self.w.city.plots if p.zone == zone]
        return min(free, key=lambda p: (math.hypot(p.x / sp - c, p.y / sp - c), p.x, p.y)) if free else None

    def _plan(self, rng: np.random.Generator) -> None:
        w = self.w
        plan = self.departments["planning"]
        busy = {pr.kind for pr in self.projects.values()}
        notes = []

        # homes
        cap = sum(w.city.buildings[b].households for b in w.occupancy)
        free = sum(w.city.buildings[b].households - len(o) for b, o in w.occupancy.items())
        coming = sum(w.city.buildings[pr.building].households_planned for pr in self.projects.values() if w.city.buildings[pr.building].kind == "home")
        full = 1 - free / max(1, cap)
        alive = w.alive()
        # planners look a year ahead: how many families will move in at today's pace?
        open_jobs = len(w.vacancies())
        weekly = min(open_jobs * 0.008, len(alive) * 0.004)
        needed = max(8.0, 0.06 * cap, PLAN_AHEAD_WEEKS * weekly)
        notes.append(f"homes {full * 100:.0f}% full")
        if free + coming < needed:
            why = (f"homes are {full * 100:.0f}% full and about {weekly * 52:.0f} more families are expected within a year."
                   if free > 8 else f"homes are {full * 100:.0f}% full and newcomers need somewhere to live.")
            plot = self._plot("residential")
            if plot is None:
                self._new_block(rng, "residential", why)
            else:
                self._housing(rng, plot, why, full)

        # jobs
        seekers = sum(1 for p in alive if p.job is None and p.unemployed_since is not None and not p.retired)
        vac = sum(1 for bid, _ in w.vacancies() if w.city.buildings[bid].status == "open")
        notes.append(f"{seekers} looking for work, {vac} open jobs")
        if seekers > vac + 15 and not busy & {"office", "factory", "shop"}:
            why = f"{seekers} people are looking for work but only {vac} jobs are open."
            zone = "industrial" if rng.random() < 0.4 else "commercial"
            plot = self._plot(zone)
            if plot is None:
                self._new_block(rng, zone, why)
            else:
                kind = "factory" if zone == "industrial" else str(rng.choice(["office", "shop", "office", "restaurant"]))
                self._start(plot, kind, 0, _developer(rng), "loan", why, "builders")

        # shops follow people: a neighbourhood needs a shop or a place to eat for every so many residents
        retail = sum(1 for b in w.city.buildings if b.kind in ("shop", "restaurant"))
        per_shop = len(alive) / max(1, retail)
        notes.append(f"{per_shop:.0f} residents per shop")
        if per_shop > PEOPLE_PER_SHOP and not busy & {"shop", "restaurant"}:
            why = f"there is one shop or restaurant for every {per_shop:.0f} residents."
            plot = self._plot("commercial")
            if plot is None:
                self._new_block(rng, "commercial", why)
            else:
                self._start(plot, "shop" if rng.random() < 0.6 else "restaurant", 0, _developer(rng), "loan", why, "builders")

        # schools
        schools = [b for b in w.city.buildings if b.kind == "school"]
        seats = sum(b.students for b in schools if b.status == "open")
        pupils = sum(len(v) for v in w.pupils.values())
        notes.append(f"{pupils} of {seats} school seats taken")
        edu = self.departments["education"]
        edu.watching = f"{pupils} pupils in {seats} seats."
        if pupils > 0.92 * seats and not any(b.status == "construction" for b in schools):
            why = f"{pupils} children fill {pupils * 100 // max(1, seats)}% of the {seats} school seats."
            plot = self._plot("residential")
            if plot is None:
                self._new_block(rng, "residential", why)
            else:
                self._start(plot, "school", 0, "Public Works Department", "city", why, "pwd")

        # places of worship
        for religion, faith in sorted(FAITHS.items()):
            kind = faith.place
            if kind is None:
                continue
            places = [b for b in w.city.buildings if b.kind == kind]
            members = sum(1 for p in w.alive() if p.religion == religion)
            if places and members / len(places) > WORSHIP_LOAD[kind] and not any(b.status == "construction" for b in places):
                plot = self._plot("residential")
                if plot is None:
                    continue
                label = TYPES[kind].label
                self._start(plot, kind, 0, f"the {religion.capitalize()} community trust", "loan",
                            f"{members} people share {len(places)} {label.lower()}{'s' if len(places) > 1 else ''}.", "trusts")
        plan.watching = "; ".join(notes) + "."

    def _housing(self, rng: np.random.Generator, plot: Plot, why: str, full: float) -> None:
        c = (self.w.city.n - 2) / 2.0
        i, j = plot.block
        r = math.hypot(i - c, j - c)
        # housing societies nearer the centre or when the city is bursting, bungalows further out
        extra = 10 if r < 4.2 or full > 0.97 else 4
        self._start(plot, "home", extra, _developer(rng), "loan", why, "builders")

    # ---- views ---------------------------------------------------------------------------------------

    def view(self) -> dict[str, Any]:
        w = self.w
        today = w.t // MINUTES_PER_DAY
        def head(d: Department) -> dict[str, Any] | None:
            if d.head is None or d.head not in w.people:
                return None
            return {"id": d.head, "name": w.people[d.head].name}
        projects = []
        for pr in self.projects.values():
            b = w.city.buildings[pr.building]
            left = max(0, round((1 - b.progress) * pr.days))
            projects.append({"building": b.id, "name": b.name, "kind": b.kind, "district": b.district, "owner": pr.owner,
                             "progress": round(b.progress, 3), "started_day": pr.started, "days_left": left, "crew": len(w.job_holders.get(b.id, [])),
                             "crew_needed": len(b.jobs), "why": pr.why})
        roads = [{"district": w.city.district_at(*rw.block), "zone": rw.zone, "progress": round(rw.progress, 3), "why": rw.why}
                 for rw in self.roadworks]
        roads += [{"street": wd.street, "progress": round(wd.progress, 3), "why": wd.why} for wd in self.widening]
        return {
            "departments": [{"key": d.key, "name": d.name, "sector": d.sector, "does": d.does, "watching": d.watching, "head": head(d),
                             "spent": round(d.spent, 2), "done": d.done} for d in self.departments.values()],
            "projects": sorted(projects, key=lambda p: -p["progress"]),
            "roadworks": roads,
            "plots": {z: sum(1 for p in w.city.plots if p.zone == z) for z in ("residential", "commercial", "industrial")},
            "finished": self.finished[-12:][::-1],
            "day": today,
        }


def _developer(rng: np.random.Generator) -> str:
    return str(rng.choice(DEVELOPERS))

