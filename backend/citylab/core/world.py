"""The world: one object that owns the whole city and moves it forward in time.

``World.advance(minutes)`` is the tick loop. Instead of asking every person every
minute what they are doing, each person sits in a priority queue keyed by the minute
their current activity ends. A tick pops only the people whose activity just ended
and lets them decide again. A city of thousands therefore costs a few thousand
decisions per simulated day, not millions, and positions between decisions are
interpolated along the planned route, never stepped.
"""

from __future__ import annotations

import heapq
import math
from typing import Any

import numpy as np

from . import lifecycle
from .brain import Brain
from .citygen import City, generate_city
from .clock import MINUTES_PER_DAY, MINUTES_PER_HOUR, MINUTES_PER_YEAR, SimTime
from .agencies import SITE_WAGE, Government
from .economy import Economy
from .events import Event, EventBus
from .faith import PLACE_KINDS, festival_on
from .health import DOCTOR_SKILL, Health
from .informal import Informal
from .mind import Mind
from .names import RELIGION_LABEL, family_name, first_name, pick_religion
from .people import ACTIVITY_NAMES, SLEEP, TRAVEL, Household, Job, Person
from .rng import Streams, stable_hash
from .routing import Router
from .transport import Transport
from .crime import Crime
from .policy import Policy
from .realworld import CAR_OWNERS, CYCLE_OWNERS, LAST_WORKING_AGE, SCOOTER_OWNERS, RETIREMENT_AGE, TOWN_POPULATION, UNEMPLOYMENT, work_force_share
from .social import SocialGraph
from .town import Town
from .weather import Weather


class World:
    def __init__(self, seed: int = 1, population: int = 2000, *, city: City | None = None, town: int = TOWN_POPULATION) -> None:
        self.seed = seed
        self.streams = Streams(seed)
        self.city = city or generate_city(seed)
        self.router = Router(self.city)
        self.weather = Weather(seed)
        self.bus = EventBus()
        self.social = SocialGraph()
        self.people: dict[int, Person] = {}
        self.households: dict[int, Household] = {}
        self.occupancy: dict[int, list[int]] = {b.id: [] for b in self.city.buildings if b.kind == "home"}
        self.job_holders: dict[int, list[int]] = {b.id: [] for b in self.city.buildings if b.jobs}
        self.pupils: dict[int, list[int]] = {b.id: [] for b in self.city.buildings if b.kind == "school"}
        self.visits: dict[int, list[int]] = {}
        self.t = 0
        self._queue: list[tuple[int, int]] = []
        self._next_pid = 0
        self._next_hh = 0
        self.daily: list[dict[str, Any]] = []  # one row of statistics per simulated day
        self.today = lifecycle.DayCounts()
        self._by_kind = {k: [b for b in self.city.buildings if b.kind == k] for k in ("restaurant", "shop", "park", "school", "hospital", "clinic", *PLACE_KINDS)}
        self.festival: tuple[str, str, str] | None = festival_on(0)
        self._near_cache: dict[tuple[int, str], list] = {}
        self._open_t, self._open = -1, {}
        self.policy = Policy()
        self.mind = Mind(self)
        self.health = Health(self)
        self.brain = Brain(self)
        self.economy = Economy(self)
        self._founded = False
        self.informal = Informal(self)
        self.government = Government(self)
        self.transport = Transport(self)
        self.crime = Crime(self)
        self.town = Town(self, max(town, population))
        self._populate(population)
        self.town.found()
        self.economy.found()
        self._founded = True

    # ---- time -------------------------------------------------------------------------

    @property
    def now(self) -> SimTime:
        return SimTime(self.t)

    def schedule(self, p: Person) -> None:
        heapq.heappush(self._queue, (p.until, p.id))

    def advance(self, minutes: int) -> None:
        end = self.t + int(minutes)
        q = self._queue
        while self.t < end:
            self.t += 1
            t = self.t
            if t % MINUTES_PER_DAY == 0:
                lifecycle.end_of_day(self)
            self.transport.tick(t)
            self.crime.tick(t)
            while q and q[0][0] <= t:
                until, pid = heapq.heappop(q)
                p = self.people.get(pid)
                if p is None or not p.alive or p.until != until:
                    continue  # stale entry: they died, left, or were rescheduled
                self.brain.decide(p, t)

    # ---- events ---------------------------------------------------------------------

    def emit(self, kind: str, text: str, people: tuple[int, ...] = (), place: int | None = None, **data: Any) -> Event:
        event = self.bus.publish(Event(t=self.t, kind=kind, text=text, people=people, place=place, data=data))
        self.mind.react(event)  # what happens to people moves their feelings and views
        return event

    # ---- people -----------------------------------------------------------------------

    def new_person(
        self, *, sex: str, born: int, household: int, last: str | None = None, parents: tuple[int, ...] = (), first: str | None = None,
        religion: str | None = None,
    ) -> Person:
        rng = self.streams("people")
        pid = self._next_pid
        self._next_pid += 1
        if religion is None:
            # children take their parents' faith; in a mixed marriage, one of the two
            faiths = sorted({self.people[q].religion for q in parents})
            religion = faiths[int(rng.integers(len(faiths)))] if faiths else pick_religion(rng)
        if first is None:
            first = first_name(rng, religion, sex)
        devotion = 0.0 if religion == "none" else float(rng.beta(2.0, 2.2))
        if parents and religion != "none":
            devotion = 0.5 * devotion + 0.5 * float(np.mean([self.people[q].devotion for q in parents]))
        traits = np.clip(rng.normal(0.5, 0.18, 5), 0.02, 0.98)
        # children take after their parents a little
        if parents:
            mean = np.mean([[self.people[q].openness, self.people[q].conscientiousness, self.people[q].extraversion,
                             self.people[q].agreeableness, self.people[q].neuroticism] for q in parents], axis=0)
            traits = np.clip(0.5 * traits + 0.5 * mean + rng.normal(0, 0.05, 5), 0.02, 0.98)
        p = Person(
            id=pid, first=first, last=last or family_name(rng, religion), sex=sex, born=born, household=household,
            religion=religion, devotion=devotion,
            openness=float(traits[0]), conscientiousness=float(traits[1]), extraversion=float(traits[2]),
            agreeableness=float(traits[3]), neuroticism=float(traits[4]), parents=parents, arrived=self.t,
        )
        p.hunger, p.energy, p.social, p.fun = (float(v) for v in rng.uniform(0.5, 0.95, 4))
        p.needs_t = self.t
        p.place = self.households[household].home
        p.until = self.t + int(rng.integers(1, 60))
        self.people[pid] = p
        self.households[household].members.append(pid)
        self.social.add_person(pid)
        for q in parents:
            self.people[q].children.append(pid)
            self.social.tie(pid, q, "parent")
            for sib in self.people[q].children:
                if sib != pid:
                    self.social.tie(pid, sib, "sibling")
        self.schedule(p)
        if self._founded:
            self.economy.open(p)
        return p

    def new_household(self, home: int, has_car: bool, has_scooter: bool = False, has_cycle: bool = False) -> Household:
        hh = Household(id=self._next_hh, home=home, members=[], has_car=has_car, has_scooter=has_scooter, has_cycle=has_cycle)
        self._next_hh += 1
        self.households[hh.id] = hh
        self.occupancy[home].append(hh.id)
        return hh

    def free_home(self, rng: np.random.Generator, near: int | None = None) -> int | None:
        free = [b for b, occ in self.occupancy.items() if len(occ) < self.city.buildings[b].households]
        if not free:
            return None
        if near is not None:
            nb = self.city.buildings[near]
            free.sort(key=lambda b: math.hypot(self.city.buildings[b].x - nb.x, self.city.buildings[b].y - nb.y))
            return free[int(rng.integers(min(5, len(free))))]
        return free[int(rng.integers(len(free)))]

    def alive(self) -> list[Person]:
        return [p for p in self.people.values() if p.alive]

    # ---- jobs and schools ---------------------------------------------------------------

    def vacancies(self) -> list[tuple[int, int]]:
        """(building, slot index) for every unfilled job. Building sites take their crews from the labour naka, day by day."""
        out = []
        for b, holders in self.job_holders.items():
            if self.city.buildings[b].status == "construction":
                continue
            for k in range(len(holders), len(self.city.buildings[b].jobs)):
                out.append((b, k))
        return out

    def hire(self, p: Person, building: int) -> None:
        b = self.city.buildings[building]
        slot = len(self.job_holders[building])
        shift = b.jobs[slot % len(b.jobs)]
        if b.kind in ("hospital", "clinic"):
            # one qualified doctor for each shift; everyone else is a nurse, an orderly or a compounder
            if not any(self.people[q].skill >= DOCTOR_SKILL and self.people[q].job.shift == shift for q in self.job_holders[building]):
                p.skill = max(p.skill, DOCTOR_SKILL + 0.08 + 0.1 * (stable_hash("doctor", p.id) % 100) / 100)
            else:
                p.skill = min(p.skill, DOCTOR_SKILL - 0.01)
        wage = (SITE_WAGE if b.status == "construction" else b.type.wage) * (0.8 + 0.6 * p.skill)
        if p.trade:  # a proper job: the cart, the homes or the naka can wait
            self.informal.drop(p)
        p.job = Job(building=building, shift=shift, wage=round(wage, 2), since=self.t)
        p.cash_job = self.economy.offers_cash(b)
        p.unemployed_since = None
        self.job_holders[building].append(p.id)

    def register(self, b) -> None:
        """A finished building joins the city: homes can be moved into, shops visited, schools enrolled in."""
        if b.kind == "home":
            self.occupancy.setdefault(b.id, [])
        if b.jobs:
            self.job_holders.setdefault(b.id, [])
        if b.kind == "school":
            self.pupils.setdefault(b.id, [])
        if b.kind in self._by_kind:
            self._by_kind[b.kind].append(b)
        self._near_cache.clear()
        if hasattr(self, "brain"):
            self.brain._near.clear()
        self._open_t = -1
        if b.jobs and b.kind not in ("school", "hospital", "police", "city_hall", "park"):
            self.economy.credit.setdefault(self.economy.company(b.id), 650.0)
            self.economy.new_books(b)

    def fire(self, p: Person) -> None:
        if p.job is not None:
            holders = self.job_holders[p.job.building]
            if p.id in holders:
                holders.remove(p.id)
            p.job = None
            p.cash_job = False

    def enrol(self, p: Person) -> bool:
        home = self.city.buildings[self.households[p.household].home]
        schools = sorted(
            self._by_kind["school"],
            key=lambda s: (len(self.pupils[s.id]) >= s.students, math.hypot(s.x - home.x, s.y - home.y), s.id),
        )
        if not schools:
            return False
        p.school = schools[0].id
        self.pupils[p.school].append(p.id)
        return True

    def unenrol(self, p: Person) -> None:
        if p.school is not None:
            if p.id in self.pupils[p.school]:
                self.pupils[p.school].remove(p.id)
            p.school = None

    # ---- places -----------------------------------------------------------------------------

    def _kind_open(self, kind: str, t: int) -> bool:
        """Every place of a kind keeps the same hours, so one look per kind per minute does."""
        if self._open_t != t:
            self._open_t, self._open = t, {}
        hit = self._open.get(kind)
        if hit is None:
            st = SimTime(t)
            places = self._by_kind.get(kind)
            hit = bool(places) and places[0].is_open(st.minute_of_day, st.is_weekend)
            self._open[kind] = hit
        return hit

    def nearest_open(self, here: int, kind: str, t: int) -> int | None:
        if not self._kind_open(kind, t):
            return None
        near = self._nearby(here, kind)
        return near[0].id if near else None

    def open_nearby(self, here: int, kind: str, t: int, k: int = 3) -> list[int]:
        """The ``k`` nearest places of a kind that are open now, nearest first."""
        if not self._kind_open(kind, t):
            return []
        return [b.id for b in self._nearby(here, kind)[:k]]

    def _nearby(self, here: int, kind: str) -> list:
        key = (here, kind)
        hit = self._near_cache.get(key)
        if hit is None:
            b0 = self.city.buildings[here]
            hit = sorted(self._by_kind[kind], key=lambda b: ((b.x - b0.x) ** 2 + (b.y - b0.y) ** 2, b.id))[:6]
            self._near_cache[key] = hit
        return hit

    # ---- founding population ----------------------------------------------------------------

    def _populate(self, target: int) -> None:
        rng = self.streams("founding")
        slots = [b for b, cap in ((b.id, b.households) for b in self.city.buildings if b.kind == "home") for _ in range(cap)]
        order = [slots[i] for i in rng.permutation(len(slots))]
        Y = MINUTES_PER_YEAR

        def born(age: float) -> int:
            return -int(age * Y) - int(rng.integers(0, Y))

        made = 0
        for home in order:
            if made >= target:
                break
            hh = self.new_household(home, has_car=bool(rng.random() < CAR_OWNERS), has_scooter=bool(rng.random() < SCOOTER_OWNERS),
                                    has_cycle=bool(self.streams("cycles").random() < CYCLE_OWNERS))
            faith = pick_religion(rng)
            last = family_name(rng, faith)
            # Indian town households: mostly parents and children, often with grandparents, and grown-up
            # children live at home until they marry (about 4 people a household, NFHS-5); few people live alone
            kind = rng.choice(["single", "couple", "family", "joint", "single_parent", "seniors"], p=[0.06, 0.1, 0.49, 0.27, 0.04, 0.04])
            adults: list[Person] = []
            if kind == "seniors":
                a = 62 + rng.integers(0, 25)
                adults.append(self.new_person(sex="F", born=born(a), household=hh.id, last=last, religion=faith))
                if rng.random() < 0.6:
                    adults.append(self.new_person(sex="M", born=born(a + rng.integers(1, 6)), household=hh.id, last=last, religion=faith))
            else:
                if kind == "single":  # mostly young men who came to town for work
                    a, first_sex = 20 + rng.integers(0, 14), "M" if rng.random() < 0.9 else "F"
                elif kind == "couple":
                    a, first_sex = 21 + rng.integers(0, 10) if rng.random() < 0.6 else 50 + rng.integers(0, 18), "F"
                else:
                    a, first_sex = 22 + rng.integers(0, 30), "F"
                adults.append(self.new_person(sex=first_sex, born=born(a), household=hh.id, last=last, religion=faith))
                if kind in ("couple", "family", "joint"):
                    adults.append(self.new_person(sex="M", born=born(a + rng.integers(1, 7)), household=hh.id, last=last, religion=faith))
            if len(adults) == 2:
                lifecycle.make_couple(self, adults[0], adults[1], announce=False)
            if kind in ("family", "joint", "single_parent"):
                mother_age = adults[0].age(0)
                for _ in range(int(rng.choice([1, 2, 3, 4], p=[0.15, 0.45, 0.3, 0.1]))):
                    child_age = mother_age - float(rng.uniform(20, 34))  # born when their mother was 20 to 34
                    if child_age < 0 or child_age >= 30:
                        continue
                    self.new_person(sex="F" if rng.random() < 0.475 else "M", born=born(child_age), household=hh.id,
                                    last=last, parents=tuple(q.id for q in adults))
            if kind == "joint":  # the husband's parents, or a widowed parent
                g = min(90, adults[1].age(0) + 24 + rng.integers(0, 8))
                elders = [self.new_person(sex="F" if rng.random() < 0.7 else "M", born=born(g - rng.integers(1, 6)), household=hh.id,
                                          last=last, religion=faith)]
                if rng.random() < 0.55 and elders[0].sex == "F":
                    elders.append(self.new_person(sex="M", born=born(g), household=hh.id, last=last, religion=faith))
                    lifecycle.make_couple(self, elders[0], elders[1], announce=False)
                adults[1].parents = tuple(q.id for q in elders)
                for e in elders:
                    e.children.append(adults[1].id)
            made += len(hh.members)

        # skills, schools, jobs, retirement
        vac = self.vacancies()
        vac_order = [vac[i] for i in rng.permutation(len(vac))]
        # the hospital and the police station are staffed first, as any real town's are
        vac_order.sort(key=lambda v: self.city.buildings[v[0]].kind not in ("hospital", "police", "clinic"))
        force = traders = 0
        for p in self.alive():
            age = p.age(0)
            p.skill = float(np.clip(rng.normal(0.25 + min(age, 45) / 90.0, 0.12), 0.05, 0.95))
            if 6 <= age < 18:
                self.enrol(p)
                continue
            if age < 18:
                continue
            share = work_force_share(age, p.sex)
            if age >= RETIREMENT_AGE:  # most have retired; some keep their shop or their trade going
                p.retired = age >= LAST_WORKING_AGE or rng.random() >= min(0.9, share * 1.6)
                if p.retired:
                    continue
            elif rng.random() >= share:
                p.at_home = True  # studying, keeping house or caring for family: not looking for paid work
                continue
            force += 1
            trade = self.informal.choose_trade(p) if age < RETIREMENT_AGE + 5 else None
            if trade is not None and self.informal.take_up(p, trade):
                traders += 1
                continue  # a cart, a round of homes, or the labour naka
            # the jobless share is of everyone working or looking, traders included
            if rng.random() >= UNEMPLOYMENT * force / max(1, force - traders) and vac_order:
                home = self.city.buildings[self.households[p.household].home]
                # take one of the nearer open jobs, as people tend to
                sample = vac_order[: 25]
                sample.sort(key=lambda bk: (math.hypot(self.city.buildings[bk[0]].x - home.x, self.city.buildings[bk[0]].y - home.y), bk))
                pick = sample[int(rng.integers(min(4, len(sample))))]
                vac_order.remove(pick)
                self.hire(p, pick[0])
            elif age >= 18:
                p.unemployed_since = 0
        # businesses start with the staff they found: posts nobody filled on day one were never advertised,
        # so the town opens with real unemployment instead of hiring it away in its first week
        for b, _ in vac_order:
            if self.city.buildings[b].kind not in ("hospital", "police", "clinic") and self.job_holders[b]:
                self.city.buildings[b].jobs = self.city.buildings[b].jobs[: len(self.job_holders[b])]
        # and if chance left too few looking for work, a few firms took on fewer people than they had room for
        short = int(round(UNEMPLOYMENT * force)) - sum(1 for p in self.alive() if p.unemployed_since is not None)
        staff = [p for p in self.alive() if p.job is not None and self.city.buildings[p.job.building].kind in ("office", "shop", "restaurant", "factory")]
        if short > 0 and staff:
            for i in sorted(rng.choice(len(staff), size=min(short, len(staff)), replace=False)):
                p = staff[int(i)]
                if len(self.job_holders[p.job.building]) < 2:
                    continue  # never the last one left at a firm
                self.city.buildings[p.job.building].jobs.remove(p.job.shift)
                self.fire(p)
                p.unemployed_since = 0

        # a starting web of acquaintances: coworkers, classmates and neighbours
        groups: dict[str, list[int]] = {}
        for p in self.alive():
            if p.job:
                groups.setdefault(f"w{p.job.building}", []).append(p.id)
            if p.school is not None:
                groups.setdefault(f"s{p.school}", []).append(p.id)
            if p.age(0) >= 14:
                groups.setdefault(f"h{self.households[p.household].home}", []).append(p.id)
        for key in sorted(groups):
            members = groups[key]
            for pid in members:
                for q in rng.choice(members, size=min(3, len(members)), replace=False):
                    if int(q) != pid:
                        self.social.tie(pid, int(q), "friend", float(rng.uniform(0.1, 0.6)))
        # everyone starts the first night asleep at home
        for p in self.alive():
            p.activity = SLEEP
        self.emit("founded", f"The city was founded with {len(self.alive())} people in {len(self.households)} households.",
                  data={"population": len(self.alive()), "households": len(self.households)})

    # ---- views for the API ------------------------------------------------------------------

    def position(self, p: Person) -> tuple[float, float]:
        if p.activity == TRAVEL and p.trip is not None:
            return p.trip.position(self.t)
        b = self.city.buildings[p.place if p.place is not None else self.households[p.household].home]
        # spread people inside their building so they do not stack on one pixel
        h = stable_hash(p.id, b.id)
        return b.x + 4 + (h % 997) / 997 * max(1.0, b.w - 8), b.y + 4 + (h // 997 % 991) / 991 * max(1.0, b.h - 8)

    def frame(self) -> dict[str, Any]:
        alive = self.alive()
        ids, xs, ys, acts, ages, places, moves = [], [], [], [], [], [], []
        t = self.t
        for p in alive:
            x, y = self.position(p)
            ids.append(p.id)
            moves.append(p.trip.leg(t) if p.activity == TRAVEL and p.trip is not None else 0)
            places.append(p.place if p.place is not None else -1)
            xs.append(round(x, 1))
            ys.append(round(y, 1))
            acts.append(p.activity)
            ages.append(int(p.age(self.t)))
        st = self.now
        return {
            "t": self.t,
            "label": st.label(),
            "day": st.day,
            "minute_of_day": st.minute_of_day,
            "weather": self.weather.at(self.t).to_dict(),
            "ids": ids,
            "x": xs,
            "y": ys,
            "activity": acts,
            "age": ages,
            "place": places,
            "move": moves,
            "buses": self.transport.buses(t),
            "traffic": self.transport.traffic(t),
            **self.crime.frame(t),
            "city_version": self.city.version,
            "sites": [[b.id, round(b.progress, 3)] for b in self.city.buildings if b.status == "construction"],
            "counts": {ACTIVITY_NAMES[k]: acts.count(k) for k in range(len(ACTIVITY_NAMES))},
        }

    def person_card(self, pid: int) -> dict[str, Any]:
        p = self.people[pid]
        t = self.t
        hh = self.households[p.household]
        def ref(q: int | None) -> dict[str, Any] | None:
            if q is None or q not in self.people:
                return None
            o = self.people[q]
            return {"id": o.id, "name": o.name, "age": int(o.age(t if o.alive else o.died or t)), "alive": o.alive}

        p.update_needs(t) if p.alive else None
        job = None
        if p.job:
            b = self.city.buildings[p.job.building]
            s = p.job.shift
            job = {"building": b.id, "place": b.name, "kind": b.kind, "wage_per_day": p.job.wage,
                   "shift": f"{s.start // 60:02d}:{s.start % 60:02d}-{s.end // 60:02d}:{s.end % 60:02d}",
                   "since_day": p.job.since // MINUTES_PER_DAY}
        friends = [{"id": q, "name": self.people[q].name, "strength": round(w, 2)} for q, w in self.social.friends(pid)[:12]]
        return {
            "id": p.id,
            "name": p.name,
            "sex": p.sex,
            "age": round(p.age(t if p.alive else p.died or t), 1),
            "stage": p.stage(t),
            "alive": p.alive,
            "home": {"building": hh.home, "name": self.city.buildings[hh.home].name, "district": self.city.buildings[hh.home].district},
            "household": [ref(q) for q in hh.members if q != pid],
            "partner": ref(p.partner),
            "parents": [ref(q) for q in p.parents],
            "children": [ref(q) for q in p.children],
            "job": job,
            "school": self.city.buildings[p.school].name if p.school is not None else None,
            "retired": p.retired,
            "at_home": p.at_home,
            "unemployed": p.unemployed_since is not None,
            "religion": RELIGION_LABEL[p.religion],
            "devotion": round(p.devotion, 2),
            "personality": {"openness": round(p.openness, 2), "conscientiousness": round(p.conscientiousness, 2),
                            "extraversion": round(p.extraversion, 2), "agreeableness": round(p.agreeableness, 2),
                            "neuroticism": round(p.neuroticism, 2)},
            "needs": {"hunger": round(p.hunger, 2), "energy": round(p.energy, 2), "social": round(p.social, 2), "fun": round(p.fun, 2)},
            "mood": round(p.mood, 2),
            "health": round(p.health, 2),
            "skill": round(p.skill, 2),
            "activity": ACTIVITY_NAMES[p.activity],
            "place": self.city.buildings[p.place].name if p.place is not None else None,
            "travel": self.transport.describe(p, t) if p.alive and p.activity == TRAVEL else None,
            "convictions": p.record,
            "in_jail_until": SimTime(p.jailed_until).label() if p.alive and p.jailed_until > t else None,
            "heading_to": self.city.buildings[p.pending.place].name if p.pending else None,
            "until": SimTime(p.until).label() if p.alive else None,
            "friends": friends,
            "friend_count": len(self.social.friends(pid)),
            "money": self.economy.person_view(pid),
            "illness": {"what": p.illness, "how": {1: "mild", 2: "moderate", 3: "serious"}[p.severity], "seen_doctor": p.seen_doctor}
            if p.alive and p.illness else None,
            "happiness": round(p.happiness, 2),
            "cash_job": p.cash_job,
            "trade": p.trade or None,
            "trade_place": self.city.buildings[p.pitch].name if p.pitch is not None else None,
            "clients": len(p.clients),
            "mind": self.mind.person(p),
            "habits": self.habits(p),
        }

    def habits(self, p: Person) -> dict[str, Any]:
        """What experience has taught them: favourite and least favourite places, and how they like to get about."""
        likes = sorted(((v, b) for b, v in p.likes.items() if b < len(self.city.buildings)), reverse=True)

        def place(v: float, b: int) -> dict[str, Any]:
            bb = self.city.buildings[b]
            return {"id": b, "name": bb.name, "kind": bb.kind, "like": round(v, 2)}

        return {
            "favourites": [place(v, b) for v, b in likes[:3] if v > 0.15],
            "avoids": [place(v, b) for v, b in likes[::-1][:2] if v < -0.15],
            "ways": {k: round(v, 2) for k, v in sorted(p.ways.items(), key=lambda kv: -kv[1])},
            "tried": len(p.likes),
        }

    def summary(self) -> dict[str, Any]:
        alive = self.alive()
        t = self.t
        working_age = [p for p in alive if 18 <= p.age(t) < 65 and p.school is None]
        employed = sum(1 for p in working_age if p.job or p.trade)
        return {
            "t": t,
            "label": self.now.label(),
            "population": len(alive),
            "town_population": self.town.population() + len(alive),
            "labour_force": employed + sum(1 for p in working_age if p.unemployed_since is not None),
            "households": sum(1 for h in self.households.values() if h.members),
            "employed": employed,
            "unemployed": sum(1 for p in working_age if p.unemployed_since is not None),
            "pupils": sum(1 for p in alive if p.school is not None),
            "retired": sum(1 for p in alive if p.retired),
            "couples": sum(1 for p in alive if p.partner is not None) // 2,
            "vacancies": len(self.vacancies()),
            "free_homes": sum(self.city.buildings[b].households - len(o) for b, o in self.occupancy.items()),
            "social": self.social.summary(),
            "events": self.bus.count,
            "city": self.city.name,
            "city_version": self.city.version,
            "projects": len(self.government.projects) + len(self.government.roadworks),
            "religions": self.religions(alive),
            "festival": {"name": self.festival[1], "faith": RELIGION_LABEL[self.festival[0]], "text": self.festival[2]} if self.festival else None,
            "hours_simulated": t // MINUTES_PER_HOUR,
        }

    def religions(self, alive: list[Person] | None = None) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in alive if alive is not None else self.alive():
            label = RELIGION_LABEL[p.religion]
            counts[label] = counts.get(label, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
