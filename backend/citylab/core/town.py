"""The rest of Kamalnagar: the 2 lakh residents who are counted rather than followed.

The map acts out a few thousand people in full, minute by minute. Everyone else lives
in the town's books, the way a real municipality knows its people: how many of each age
live in each neighbourhood, how many work, study, are ill, and what happened to them
today. Each night the books move on:

* **Life and death follow real Indian rates.** Babies are born, people die by age,
  everyone grows a day older, and new families move in, at the rates the Sample
  Registration System measures for Indian towns.
* **Everything else follows the people on the map.** The map is a living sample of the
  town, like a survey. If one in two hundred of the people on the map fell ill today,
  about one in two hundred of everyone else did too. Small samples are noisy, so each
  rate is blended with the real-world figure (see realworld.py): the more the map has
  seen, the more it counts. Each day's numbers are then drawn at random around those
  rates, so the town has its own good and bad days rather than copying the map times 40.
* **Their money flows through the city's own budget.** Their income tax, property tax
  and water bills come in, and the city pays their teachers, police, pensions and buses,
  at the same rate per person as for the people on the map.

The people on the map are residents too: town totals are the books plus the map.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any

import numpy as np

from . import realworld as rw
from .clock import SimTime
from .health import DOCTOR_SKILL

if TYPE_CHECKING:
    from .world import World

DAYS = 365.0
BANDS = rw.AGE_BANDS
N_BANDS = len(BANDS)
PRIOR_DAYS = 30  # the real-world figure counts as much as a month of the map
RARE_PRIOR_DAYS = 365  # ...or a year of it, for events the map sees only a few times a month
WINDOW = 30  # days of the map's own record that set today's rates

# the city's recurring money, per person, that the rest of the town pays and receives too
# (one-off works like a new camera or a widened road happen on the map only, and the buses on the map
# are the town's whole bus network, so their diesel is already paid in full)
TOWN_INCOME = {
    "income tax": "taxpayers", "business tax": "people", "sales tax": "people", "property tax": "households",
    "water bills": "households", "bus fares": "people", "hospital fees": "visits",
}
RULED = ("income tax", "bus fares", "unemployment benefit")
BASE_KEY = {"people": "population", "households": "households", "taxpayers": "taxpayers", "retired": "retired", "unemployed": "unemployed",
            "visits": "hospital_visits"}
SALARIED = ("office", "school", "hospital", "police", "city_hall", "bank", "court")  # regular, salaried work
TOWN_SPENDING = {
    "wages": "people", "pensions": "retired", "unemployment benefit": "unemployed",
    "water supply": "people", "medicines": "visits", "police patrols": "people",
}


class Town:
    def __init__(self, world: World, total: int = rw.TOWN_POPULATION) -> None:
        self.w = world
        self.rng = world.streams("town")
        self.total = total
        # people[district] = array (age band, sex) of counts, sex 0 = men, 1 = women
        self.people: dict[str, np.ndarray] = {}
        self.faiths: dict[str, float] = {}
        self.today: dict[str, Any] = {}
        self.history: deque[dict[str, Any]] = deque(maxlen=400)

    # ---- founding --------------------------------------------------------------------------

    def found(self) -> None:
        """Fill the books so that books + map = the whole town, spread like the people on the map."""
        w = self.w
        alive = w.alive()
        rest = max(0, self.total - len(alive))
        by_district: dict[str, int] = {}
        for p in alive:
            d = w.city.buildings[w.households[p.household].home].district
            by_district[d] = by_district.get(d, 0) + 1
        districts = sorted(by_district) or sorted({b.district for b in w.city.buildings})
        weights = np.array([by_district.get(d, 1) for d in districts], dtype=float)
        counts = self._split(rest, weights)
        shares = np.outer(np.array(rw.AGE_SHARES), np.array([rw.MALE_SHARE, 1.0 - rw.MALE_SHARE]))
        for d, n in zip(districts, counts):
            self.people[d] = self._split(int(n), shares.ravel()).reshape(N_BANDS, 2).astype(np.int64)
        faiths: dict[str, int] = w.religions(alive)
        n = max(1, sum(faiths.values()))
        self.faiths = {k: v / n for k, v in faiths.items()}

    def _split(self, n: int, weights: np.ndarray) -> np.ndarray:
        """``n`` people shared out by weight, whole people only, adding up exactly."""
        raw = n * weights / weights.sum()
        out = np.floor(raw).astype(np.int64)
        for i in np.argsort(-(raw - out))[: n - int(out.sum())]:
            out[i] += 1
        return out

    # ---- who lives in the books --------------------------------------------------------------

    def population(self) -> int:
        return int(sum(a.sum() for a in self.people.values()))

    def by_age(self) -> np.ndarray:
        return sum(self.people.values(), np.zeros((N_BANDS, 2), dtype=np.int64))

    def everyone_by_age(self) -> np.ndarray:
        """The whole town by age band and sex: the books plus the people on the map."""
        a = self.by_age().copy()
        t = self.w.t
        for p in self.w.alive():
            age = p.age(t)
            i = next((k for k, (lo, hi) in enumerate(BANDS) if lo <= age < hi), N_BANDS - 1)
            a[i, 0 if p.sex == "M" else 1] += 1
        return a

    def _status(self, unemployment: float) -> dict[str, float]:
        """Who works, studies, looks for work or has retired, from the age and sex of everyone in the books."""
        a = self.by_age()
        force = 0.0
        for i, band in enumerate(BANDS):
            men, women = rw.IN_WORK_FORCE.get(band, (0.0, 0.0))
            force += a[i, 0] * men + a[i, 1] * women
        old = a[N_BANDS - 1].sum()
        old_working = a[N_BANDS - 1, 0] * rw.IN_WORK_FORCE[BANDS[-1]][0] + a[N_BANDS - 1, 1] * rw.IN_WORK_FORCE[BANDS[-1]][1]
        students = sum(a[i].sum() * rw.IN_SCHOOL.get(band, 0.0) for i, band in enumerate(BANDS))
        unemployed = force * unemployment
        return {"labour_force": force, "employed": force - unemployed, "unemployed": unemployed,
                "students": students, "retired": old - old_working, "children": float(a[0].sum())}

    # ---- rates: the map's own record, blended with the real world -----------------------------

    def _rate(self, rows: list[dict[str, Any]], key: str, per: str, prior: float, prior_days: float = PRIOR_DAYS) -> float:
        """Events per person (or per ``per``) per day: the map's last month, pulled towards the real figure."""
        seen = sum(float(r.get(key) or 0) for r in rows)
        exposure = sum(float(r.get(per) or 0) for r in rows)
        weight = prior_days * exposure / len(rows) if rows else 1.0
        return (seen + prior * weight) / max(1.0, exposure + weight)

    def _share(self, rows: list[dict[str, Any]], part: str, whole: str, prior: float, prior_days: float = PRIOR_DAYS) -> float:
        """A share of people (the unemployed, the ill), the same way."""
        return self._rate(rows, part, whole, prior, prior_days)

    # ---- every night -----------------------------------------------------------------------

    def nightly(self, map_row: dict[str, Any]) -> dict[str, Any]:
        """Move the books on by a day. ``map_row`` is tonight's row for the people on the map."""
        w = self.w
        rng = self.rng
        rows = (list(w.daily[-(WINDOW - 1):]) + [map_row]) if map_row else list(w.daily[-WINDOW:])
        today = {"born": 0, "died": 0, "arrived": 0}

        # life and death, by real rates
        for d, a in self.people.items():
            for i in range(N_BANDS):
                for s in (0, 1):
                    n = int(a[i, s])
                    if n <= 0:
                        continue
                    died = int(rng.binomial(n, rw.DEATH_RATE_BY_AGE[i] / DAYS))
                    a[i, s] -= died
                    today["died"] += died
                    lo, hi = BANDS[i]
                    if i + 1 < N_BANDS:  # a birthday that moves them into the next age band
                        older = int(rng.binomial(int(a[i, s]), 1.0 / ((hi - lo) * DAYS)))
                        a[i, s] -= older
                        a[i + 1, s] += older
            mothers = a[2, 1] + a[3, 1] * 14 / 15  # women aged 18 to 44
            per_mother = rw.BIRTHS_PER_1000 / 1000 / max(1e-9, self._mother_share())
            born = int(rng.binomial(int(mothers), min(1.0, per_mother / DAYS)))
            boys = int(rng.binomial(born, rw.MALE_SHARE))
            a[0, 0] += boys
            a[0, 1] += born - boys
            today["born"] += born

        # newcomers: jobs and homes in town pull them in, as for the people on the map
        pop = self.population()
        pull = 1.0
        if map_row:
            seekers = float(map_row.get("unemployed") or 0)
            vacancies = float(map_row.get("vacancies") or 0)
            pull = float(np.clip(1.0 + (vacancies - seekers) / max(1.0, float(map_row.get("population") or 1)) * 5, 0.4, 2.0))
            if float(map_row.get("free_homes") or 0) <= 0:
                pull *= 0.3
        arrived = int(rng.poisson(pop * rw.NET_MIGRATION / DAYS * pull))
        districts = sorted(self.people)
        sizes = np.array([self.people[d].sum() for d in districts], dtype=float)
        ages = np.array(rw.MIGRANT_AGES) / sum(rw.MIGRANT_AGES)
        for _ in range(arrived):
            d = districts[int(rng.choice(len(districts), p=sizes / sizes.sum()))]
            i = int(rng.choice(N_BANDS, p=ages))
            self.people[d][i, int(rng.random() >= rw.MALE_SHARE)] += 1
        today["arrived"] = arrived

        # everything else follows the people on the map
        pop = self.population()
        unemployment = self._share(rows, "unemployed", "labour_force", rw.UNEMPLOYMENT) if rows else rw.UNEMPLOYMENT
        status = self._status(unemployment)
        fall_ill = self._rate(rows, "fell_ill", "population", rw.FALL_ILL_PER_DAY)
        visits = self._rate(rows, "hospital_visits", "population", rw.DOCTOR_VISITS_PER_DAY)
        ill = self._share(rows, "sick", "population", rw.ILL_AT_ANY_TIME)
        # thefts are rare on the map (a handful a month), so the real figure counts as much as a year of it
        thefts = self._rate(rows, "crimes", "population", rw.THEFTS_PER_LAKH / rw.REPORTED / 1e5 / DAYS, RARE_PRIOR_DAYS)
        reported = self._share(rows, "crimes_reported", "crimes", rw.REPORTED, RARE_PRIOR_DAYS)
        cleared = self._share(rows, "arrests", "crimes_reported", rw.CLEARED, RARE_PRIOR_DAYS)
        today.update({
            "fell_ill": int(rng.poisson(pop * fall_ill)),
            "hospital_visits": int(rng.poisson(pop * visits)),
            "sick": int(round(pop * ill)),
            "crimes": int(rng.poisson(pop * thefts)),
        })
        today["crimes_reported"] = int(rng.binomial(today["crimes"], min(1.0, reported)))
        today["arrests"] = int(rng.binomial(today["crimes_reported"], min(1.0, cleared)))
        today.update({k: int(round(v)) for k, v in status.items()})
        today["population"] = pop
        today["households"] = int(round(pop / rw.HOUSEHOLD_SIZE))
        today["unemployment"] = unemployment
        self._money(rows, today)
        self.today = today
        self.history.append(today)
        return today

    @staticmethod
    def _mother_share() -> float:
        return (1.0 - rw.MALE_SHARE) * (rw.AGE_SHARES[2] + rw.AGE_SHARES[3] * 14 / 15)

    def _money(self, rows: list[dict[str, Any]], today: dict[str, Any]) -> None:
        """The rest of the town's taxes and bills come into the city budget, and its services are paid out of it."""
        if not rows:
            return
        econ = self.w.economy
        recent = rows[-7:]
        n = len(recent)

        def avg(key: str) -> float:
            return sum(float(r.get(key) or 0) for r in recent) / n

        base = {"people": avg("population"), "households": avg("households"), "taxpayers": avg("taxpayers"),
                "retired": avg("retired"), "unemployed": avg("unemployed"), "visits": avg("hospital_visits")}
        mine = {"people": today["population"], "households": today["households"],
                "taxpayers": today["employed"] * (1.0 - self._cash_share(recent)), "retired": today["retired"],
                "unemployed": today["unemployed"], "visits": today["hospital_visits"]}
        took = spent = 0.0
        for purposes, into_city in ((TOWN_INCOME, True), (TOWN_SPENDING, False)):
            for purpose, per in purposes.items():
                # flows the council's rules set (tax, fares, benefits) follow today's rules; the rest a week's average
                days = recent[-1:] if purpose in RULED else recent
                flow = sum(float((r.get("map_city_in" if into_city else "map_city_out") or {}).get(purpose, 0.0)) for r in days) / len(days)
                base_now = base[per] if days is recent else float(days[-1].get(BASE_KEY[per]) or 0)
                if not flow or not base_now:
                    continue
                amount = flow / base_now * mine[per]
                if into_city:
                    took += econ.transfer("outside", "city", amount, purpose, books=True)
                else:
                    spent += econ.transfer("city", "outside", amount, purpose, books=True)
        # the state's grants come for every resident, on the map or not
        everyone = today["population"] + len(self.w.alive())
        took += econ.transfer("outside", "city", everyone * rw.STATE_GRANT_PER_PERSON_YEAR / DAYS, "state grants", books=True)
        today["city_in"] = round(took, 2)
        today["city_out"] = round(spent, 2)

    @staticmethod
    def _cash_share(rows: list[dict[str, Any]]) -> float:
        cash = sum(float(r.get("cash_workers") or 0) for r in rows)
        payers = sum(float(r.get("taxpayers") or 0) for r in rows)
        return cash / max(1.0, cash + payers)

    # ---- what the books show ----------------------------------------------------------------

    def services(self, total: int) -> dict[str, int]:
        """How many police, doctors and teachers a town this size has, at real Indian ratios."""
        pupils = self.today.get("students", 0)
        return {"police": int(round(total * rw.POLICE_PER_LAKH / 1e5)), "doctors": int(round(total * rw.DOCTORS_PER_1000 / 1000)),
                "teachers": int(round(pupils / rw.PUPILS_PER_TEACHER))}

    def view(self) -> dict[str, Any]:
        w = self.w
        map_people = len(w.alive())
        books = self.population()
        total = books + map_people
        a = self.everyone_by_age()
        return {
            "population": total, "on_map": map_people, "in_books": books,
            "households": self.today.get("households", 0) + sum(1 for h in w.households.values() if h.members),
            "districts": {d: int(v.sum()) for d, v in sorted(self.people.items())},
            "ages": {label: int(a[i].sum()) for i, label in enumerate(rw.AGE_LABELS)},
            "women_per_1000_men": int(round(1000 * a[:, 1].sum() / max(1, a[:, 0].sum()))),
            "faiths": {k: int(round(v * total)) for k, v in self.faiths.items()},
            "today": self.today,
            "services": self.services(total),
            "date": SimTime(w.t).label(),
        }

    def compare(self) -> list[dict[str, Any]]:
        """Kamalnagar's last month next to a real Indian town of the same size."""
        w = self.w
        rows = list(w.daily[-WINDOW:])
        alive = w.alive()
        t = w.t
        a = self.everyone_by_age()
        total = max(1, int(a.sum()))
        out: list[dict[str, Any]] = []

        def add(label: str, ours: float | None, real: float, unit: str, source: str, digits: int = 0) -> None:
            out.append({"label": label, "kamalnagar": None if ours is None else round(float(ours), digits), "real": round(float(real), digits),
                        "unit": unit, "source": source})

        add("People", total, rw.TOWN_POPULATION, "", "a town of 2 lakh")
        add("Women per 1,000 men", 1000 * a[:, 1].sum() / max(1, a[:, 0].sum()), 1000 * (1 - rw.MALE_SHARE) / rw.MALE_SHARE, "", "Census 2011, towns")
        add("Children under 18", 100 * a[:2].sum() / total, 100 * (rw.AGE_SHARES[0] + rw.AGE_SHARES[1]), "%", "Census 2011, towns")
        add("Aged 60 and over", 100 * a[-1].sum() / total, 100 * rw.AGE_SHARES[-1], "%", "Census 2011, towns")
        homes = sum(1 for h in w.households.values() if h.members)
        add("People per household", len(alive) / max(1, homes), rw.HOUSEHOLD_SIZE, "", "NFHS-5, towns", 1)
        if rows and rows[-1].get("town_population"):
            n, pop = len(rows), float(rows[-1]["town_population"])
            year = DAYS / n

            def town(key: str) -> float:
                return sum(float(r.get(key) or 0) for r in rows)

            add("Births per 1,000 a year", 1000 * town("town_births") * year / pop, rw.BIRTHS_PER_1000, "", "SRS, towns", 1)
            add("Deaths per 1,000 a year", 1000 * town("town_deaths") * year / pop, rw.DEATHS_PER_1000, "", "SRS, towns", 1)
            r = rows[-1]
            add("Unemployment", 100 * r["town_unemployed"] / max(1, r["town_unemployed"] + r["town_employed"]), 100 * rw.UNEMPLOYMENT, "%",
                "PLFS 2023-24, towns", 1)
            add("Thefts registered per lakh a year", 1e5 * town("town_crimes_reported") * year / pop, rw.THEFTS_PER_LAKH, "", "NCRB 2022")
            add("Ill right now", 100 * r["town_sick"] / pop, 100 * rw.ILL_AT_ANY_TIME, "%", "NSS 75th round", 1)
        adults = [p for p in alive if p.age(t) >= 18]
        working = [p for p in adults if p.job is not None or p.unemployed_since is not None]
        add("Adults working or looking for work", 100 * len(working) / max(1, len(adults)), 100 * self._force_share(), "%", "PLFS 2023-24, towns")
        salaried = [p.job.wage for p in alive if p.job is not None and w.city.buildings[p.job.building].kind in SALARIED]
        if salaried:
            add("A salaried job's monthly pay", 26 * sum(salaried) / len(salaried), rw.MONTHLY_EARNINGS["regular"], "₹", "PLFS 2023-24, towns")
        add("Police per lakh people", self.services(total)["police"] * 1e5 / total, rw.POLICE_PER_LAKH, "", "BPR&D 2023")
        hosp = [b.id for b in w.city.buildings if b.kind == "hospital"]
        doctors = sum(1 for p in alive if p.job is not None and p.job.building in hosp and p.skill >= DOCTOR_SKILL)
        add("Doctors per 1,000 (on the map)", 1000 * doctors / max(1, len(alive)), rw.DOCTORS_PER_1000, "", "NMC", 1)
        hhs = [h for h in w.households.values() if h.members]
        add("Homes with a scooter or motorbike", 100 * sum(h.has_scooter for h in hhs) / max(1, len(hhs)), 100 * rw.SCOOTER_OWNERS, "%", "NFHS-5, towns")
        add("Homes with a car", 100 * sum(h.has_car for h in hhs) / max(1, len(hhs)), 100 * rw.CAR_OWNERS, "%", "NFHS-5, towns")
        happy = rows[-1].get("happiness") if rows else None
        add("Happiness (life ladder, out of 100)", happy, rw.HAPPINESS, "", "World Happiness Report 2024")
        return out

    @staticmethod
    def _force_share() -> float:
        """The share of adults (18+) in the labour force in a real town of this age mix."""
        num = den = 0.0
        for i, band in enumerate(BANDS[2:], start=2):
            men, women = rw.IN_WORK_FORCE.get(band, (0.0, 0.0))
            num += rw.AGE_SHARES[i] * (rw.MALE_SHARE * men + (1 - rw.MALE_SHARE) * women)
            den += rw.AGE_SHARES[i]
        return num / den

    def row(self, map_row: dict[str, Any], books: dict[str, Any]) -> dict[str, Any]:
        """Tonight's town-wide totals: the books plus the people on the map."""
        def both(key: str, mine: str | None = None) -> int:
            return int(round(float(map_row.get(key) or 0) + float(books.get(mine or key) or 0)))

        return {
            "town_population": both("population"),
            "town_households": both("households"),
            "town_births": both("births", "born"),
            "town_deaths": both("deaths", "died"),
            "town_arrived": both("arrived"),
            "town_left": int(map_row.get("left") or 0),
            "town_employed": both("employed"),
            "town_unemployed": both("unemployed"),
            "town_retired": both("retired"),
            "town_pupils": both("pupils", "students"),
            "town_fell_ill": both("fell_ill"),
            "town_sick": both("sick"),
            "town_hospital_visits": both("hospital_visits"),
            "town_crimes": both("crimes"),
            "town_crimes_reported": both("crimes_reported"),
            "town_arrests": both("arrests"),
        }


__all__ = ["Town"]

