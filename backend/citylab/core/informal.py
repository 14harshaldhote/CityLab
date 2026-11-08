"""The informal economy: work with no office, no payslip and no tax.

About half of the work in Indian towns is like this (PLFS 2023-24). Three kinds of it
live in Kamalnagar, next to the cash-in-hand jobs in shops and on building sites:

* **Street vendors** push a cart of vegetables and fruit to the same pitch every
  morning, near a market or a park, and sell until evening. Families buy their
  sabzi from the nearest cart instead of the shop, and the vendor buys stock at the
  mandi at dawn. Takings go up and down with how many families live nearby. About
  two in every hundred town people are street vendors (National Policy on Urban
  Street Vendors).
* **Domestic workers** (the kaamwali bai) clean and cook in four or five better-off
  homes every morning, for about ₹2,500 a month from each. Families that can no
  longer afford it let them go, and families doing well take one on.
* **Day labourers** stand at the labour naka at seven in the morning. Builders (whose
  crews all come from the naka), factories and shops that need loading done, and
  families who need help moving house or painting, pick people for the day at
  about ₹550, cash. Some mornings there is no work, and they
  go home with nothing.

Nobody here pays income tax, and nobody gets a pension or sick pay: a bad week is
simply a bad week. People who can't find a job take up a trade after a while, and
many leave it as soon as a proper job comes along.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from .clock import MINUTES_PER_DAY, SimTime
from .people import WORK

if TYPE_CHECKING:
    from .people import Person
    from .world import World

TRADES = ("vendor", "maid", "labourer")
TRADE_WORDS = {"vendor": "a street vendor", "maid": "a domestic worker", "labourer": "a day labourer"}
# share of new workers who end up in each trade, by sex (men, women): vendors and labourers are mostly men, domestic workers women
TAKE_UP = {"vendor": (0.06, 0.03), "maid": (0.0, 0.16), "labourer": (0.05, 0.02)}
VEG_PER_PERSON = 15.0  # vegetables and fruit, a day: bought from a cart when there's one nearby
MANDI_SHARE = 0.6  # what the vendor paid for it at the wholesale market at dawn
VENDING_FEE = 10.0  # a day, to the town vending committee
VENDOR_REACH = 1200.0  # metres families will walk to a cart
MAID_PER_DAY = 85.0  # from each home: about ₹2,500 a month
MAID_HOMES = 5
MAID_RICH, MAID_POOR = 60_000.0, 20_000.0  # family savings at which a maid is taken on, and let go
DAY_WAGE = 550.0
ODD_JOBS = 0.01  # share of homes that need a hand for the day: moving house, painting, a repair
PITCH_KINDS = ("shop", "park", "restaurant", "hospital", "school")
QUIT_AFTER = 30  # days of looking for work before people start taking up a trade


class Informal:
    def __init__(self, world: World) -> None:
        self.w = world
        self.rng = world.streams("informal")
        self.rounds: dict[int, int] = defaultdict(int)  # maid -> homes done today
        self.worked: dict[int, int] = {}  # person -> where they worked today
        self.hired: dict[int, int | None] = {}  # day labourer -> site picked for today (None: nobody picked them)
        self.demand: list[tuple[str, int]] | None = None  # today's jobs at the naka: (payer account, site)
        self.history: list[dict[str, Any]] = []
        self.veg_homes: set[int] = set()  # households that bought their vegetables from a cart today
        self._naka: int | None = None
        self._payer: dict[int, str] = {}  # day labourer -> who pays them today
        self._matched = False  # families have found their maids (done in full on the first night)

    # ---- who does what -------------------------------------------------------------------------

    @property
    def naka(self) -> int:
        """The labour naka: the corner by the market nearest the centre."""
        if self._naka is None:
            city = self.w.city
            c = city.size / 2
            shops = [b for b in city.buildings if b.kind in ("shop", "park")] or city.buildings
            self._naka = min(shops, key=lambda b: (math.hypot(b.x - c, b.y - c), b.id)).id
        return self._naka

    def take_up(self, p: Person, trade: str) -> bool:
        w = self.w
        p.trade = trade
        p.unemployed_since = None
        p.pitch = None
        p.clients = []
        home = w.city.buildings[w.households[p.household].home]
        if trade == "vendor":
            spots = sorted((b for b in w.city.buildings if b.kind in PITCH_KINDS and b.status == "open"),
                           key=lambda b: (math.hypot(b.x - home.x, b.y - home.y), b.id))[:4]
            if not spots:
                p.trade = ""
                return False
            p.pitch = spots[int(self.rng.integers(len(spots)))].id
        elif trade == "labourer":
            p.pitch = self.naka
        return True

    def drop(self, p: Person) -> None:
        """They found a proper job, retired or left: the trade goes with them."""
        if p.trade == "maid":
            for h in p.clients:
                hh = self.w.households.get(h)
                if hh is not None and hh.maid == p.id:
                    hh.maid = None
        p.trade, p.pitch, p.clients = "", None, []

    def choose_trade(self, p: Person) -> str | None:
        """For a new worker at the founding: a trade, or None for an ordinary job."""
        u = float(self.rng.random())
        for trade in TRADES:
            share = TAKE_UP[trade][0 if p.sex == "M" else 1]
            if u < share:
                return trade
            u -= share
        return None

    # ---- the working day -----------------------------------------------------------------------

    def option(self, p: Person, t: int) -> tuple[float, int, int, int] | None:
        """Their trade's call on their time right now, if any, as a brain option."""
        st = SimTime(t)
        day, mod = st.day, st.minute_of_day
        if (day + p.id) % 7 == 0:  # a day off a week
            return None
        start = day * MINUTES_PER_DAY
        w = self.w
        if p.trade == "vendor" and p.pitch is not None:
            if 6 * 60 + 30 <= mod < 16 * 60 and p.worked_day != day:
                return 4.0 + p.conscientiousness, WORK, p.pitch, start + 19 * 60 + 30
        elif p.trade == "maid" and p.clients:
            k = self.rounds.get(p.id, 0) if p.worked_day == day else 0
            if 6 * 60 + 30 <= mod < 12 * 60 + 30 and k < len(p.clients):
                hh = w.households.get(p.clients[k])
                if hh is not None and hh.members:
                    return 4.2 + p.conscientiousness, WORK, hh.home, t + 70
        elif p.trade == "labourer":
            if 6 * 60 + 30 <= mod < 8 * 60 + 30 and p.worked_day != day:
                return 4.0 + p.conscientiousness, WORK, self.naka, start + 9 * 60 + 30
            site = self.hired.get(p.id)
            if site is not None and p.worked_day == day and mod < 16 * 60 and p.place != site:
                return 5.0, WORK, site, start + 18 * 60
        return None

    def start(self, p: Person, place: int, t: int) -> None:
        """They've arrived at work: the cart is set up, the maid lets herself in, the labourer joins the crowd at the naka."""
        w = self.w
        if p.trade == "maid":
            self.rounds[p.id] = self.rounds.get(p.id, 0) + 1
            self.worked[p.id] = place
        elif p.trade == "labourer":
            if place == self.naka and p.id not in self.hired:
                self.hired[p.id] = self._pick(p)
            elif place != self.naka:
                self.worked[p.id] = place
                if place in w.government.projects:
                    w.economy.attendance[place].append(p.id)  # one more pair of hands on the site
        else:
            self.worked[p.id] = place

    def jobs_today(self) -> list[tuple[str, int]]:
        """This morning's work at the naka, (who pays, where), in the order it's handed out."""
        if self.demand is None:
            w = self.w
            demand: list[tuple[str, int]] = []
            # every building site's crew comes from the naka
            for bid, pr in sorted(w.government.projects.items()):
                b = w.city.buildings[bid]
                short = len(b.jobs) - len(w.job_holders.get(bid, []))
                demand += [(pr.account, bid)] * max(0, short)
            # factories and shops hire a hand or two for loading and unloading
            for b in w.city.buildings:
                if b.status == "open" and (b.kind == "factory" or b.kind == "shop" and self.rng.random() < 0.3):
                    demand.append((w.economy.company(b.id), b.id))
            # and families need help moving house, painting, a repair
            homes = [h for h in w.households.values() if h.members]
            n = int(self.rng.poisson(len(homes) * ODD_JOBS))
            for i in self.rng.choice(len(homes), size=min(n, len(homes)), replace=False) if homes else []:
                hh = homes[int(i)]
                payer = w.economy._richest_adult(hh.members)
                if payer is not None and w.economy.balance[w.economy.person(payer)] > 20_000:
                    demand.append((w.economy.person(payer), hh.home))
            order = self.rng.permutation(len(demand))
            self.demand = [demand[int(i)] for i in order]
        return self.demand

    def _pick(self, p: Person) -> int | None:
        """At the naka: does a builder, a factory or a family pick them today?"""
        demand = self.jobs_today()
        if not demand:
            return None
        account, site = demand.pop()
        self._payer[p.id] = account
        return site

    # ---- at night: pay and settle --------------------------------------------------------------

    def daily(self) -> dict[str, Any]:
        """Everyone is paid for today's work, in cash. Runs before the books close."""
        w = self.w
        econ = w.economy
        alive = {p.id: p for p in w.alive()}
        vendors = [p for p in alive.values() if p.trade == "vendor" and self.worked.get(p.id) == p.pitch]
        takings: dict[int, float] = defaultdict(float)
        self.veg_homes = set()
        if vendors:
            spots = defaultdict(list)
            for v in vendors:
                spots[v.pitch].append(v)
            for hh in w.households.values():
                if not hh.members:
                    continue
                home = w.city.buildings[hh.home]
                best = min(spots, key=lambda b: (math.hypot(w.city.buildings[b].x - home.x, w.city.buildings[b].y - home.y), b))
                bb = w.city.buildings[best]
                if math.hypot(bb.x - home.x, bb.y - home.y) > VENDOR_REACH:
                    continue
                payer = econ._richest_adult(hh.members)
                if payer is None:
                    continue
                at = spots[best]
                v = at[(hh.id * 7 + SimTime(w.t).day) % len(at)]  # families have their own cart, and it rotates a little
                paid = econ.transfer(econ.person(payer), econ.person(v.id), VEG_PER_PERSON * len(hh.members), "vegetables from street vendors")
                if paid:
                    takings[v.id] += paid
                    self.veg_homes.add(hh.id)
            for v in vendors:
                econ.transfer(econ.person(v.id), "outside", takings[v.id] * MANDI_SHARE, "mandi stock")
                econ.transfer(econ.person(v.id), "city", VENDING_FEE, "vending fees")
        maid_pay = 0.0
        for p in alive.values():
            if p.trade != "maid" or not self.rounds.get(p.id):
                continue
            for h in p.clients[: self.rounds[p.id]]:
                hh = w.households.get(h)
                payer = econ._richest_adult(hh.members) if hh is not None and hh.members else None
                if payer is not None:
                    maid_pay += econ.transfer(econ.person(payer), econ.person(p.id), MAID_PER_DAY, "domestic work")
        labour_pay = 0.0
        hired = 0
        for pid, site in self.hired.items():
            p = alive.get(pid)
            if p is None or site is None or self.worked.get(pid) != site:
                continue
            account = self._payer.get(pid)
            if account is not None:
                labour_pay += econ.transfer(account, econ.person(pid), DAY_WAGE, "day labour")
                hired += 1
        at_naka = sum(1 for v in self.hired.values())
        row = {
            "vendors": sum(1 for p in alive.values() if p.trade == "vendor"),
            "maids": sum(1 for p in alive.values() if p.trade == "maid"),
            "labourers": sum(1 for p in alive.values() if p.trade == "labourer"),
            "vendor_takings": round(sum(takings.values()), 2),
            "maid_pay": round(maid_pay, 2),
            "labour_pay": round(labour_pay, 2),
            "at_naka": at_naka,
            "naka_hired": hired,
            "homes_with_maid": sum(1 for h in w.households.values() if h.members and h.maid is not None),
        }
        self.history.append(row)
        self.history = self.history[-30:]
        self.rounds = defaultdict(int)
        self.worked = {}
        self.hired = {}
        self._payer = {}
        self.demand = None
        return row

    def nightly(self, alive: list[Person]) -> None:
        """Families take on or let go of a maid; people who've looked for work a long time take up a trade."""
        w = self.w
        econ = w.economy
        t = w.t
        # families doing well take on help; families short of money let her go
        maids = [p for p in alive if p.trade == "maid"]
        for hh in sorted(w.households.values(), key=lambda h: h.id):
            if not hh.members:
                continue
            savings = sum(max(0.0, econ.balance[econ.person(q)]) for q in hh.members if w.people[q].age(t) >= 18)
            if hh.maid is not None:
                m = w.people.get(hh.maid)
                if m is None or not m.alive or m.trade != "maid" or savings < MAID_POOR:
                    if m is not None and hh.id in m.clients:
                        m.clients.remove(hh.id)
                    hh.maid = None
                continue
            if savings < MAID_RICH or (self._matched and self.rng.random() > 0.05) or not maids:
                continue
            home = w.city.buildings[hh.home]
            free = [m for m in maids if len(m.clients) < MAID_HOMES]
            if not free:
                continue
            m = min(free, key=lambda m: (math.hypot(w.city.buildings[w.households[m.household].home].x - home.x,
                                                    w.city.buildings[w.households[m.household].home].y - home.y), m.id))
            m.clients.append(hh.id)
            hh.maid = m.id
        self._matched = True
        # long searches end in a trade
        for p in alive:
            if p.trade or p.job is not None or p.unemployed_since is None or p.retired or p.at_home:
                continue
            if t - p.unemployed_since < QUIT_AFTER * MINUTES_PER_DAY or self.rng.random() > 0.04:
                continue
            trade = "maid" if p.sex == "F" and self.rng.random() < 0.6 else "vendor" if self.rng.random() < 0.55 else "labourer"
            if self.take_up(p, trade):
                w.emit("trade", f"{p.name} gave up looking for a job and became {TRADE_WORDS[trade]}"
                       + (f" near {w.city.buildings[p.pitch].name.split(',')[0]}." if trade == "vendor" else "."), (p.id,), p.pitch)

    # ---- views ---------------------------------------------------------------------------------

    def view(self) -> dict[str, Any]:
        w = self.w
        alive = w.alive()
        rows = self.history[-7:]
        n = max(1, len(rows))
        workers = [p for p in alive if p.job is not None or p.trade]

        def avg(key: str) -> float:
            return round(sum(r[key] for r in rows) / n, 1)

        def per(trade: str, pay: str) -> float | None:
            k = sum(r[trade] for r in rows)
            return round(sum(r[pay] for r in rows) / k, 0) if k else None

        return {
            "vendors": sum(1 for p in alive if p.trade == "vendor"),
            "maids": sum(1 for p in alive if p.trade == "maid"),
            "labourers": sum(1 for p in alive if p.trade == "labourer"),
            "cash_in_hand": sum(1 for p in alive if p.job is not None and p.cash_job),
            "workers": len(workers),
            "homes_with_maid": rows[-1]["homes_with_maid"] if rows else 0,
            "a_day": {"vendor": per("vendors", "vendor_takings"), "maid": per("maids", "maid_pay"),
                      "labourer": per("naka_hired", "labour_pay")},
            "naka": {"waiting": avg("at_naka"), "picked": avg("naka_hired")},
            "naka_place": w.city.buildings[self.naka].name,
        }


def informal_share(w: World) -> float:
    """Share of workers in informal work: a trade, or a job paid cash in hand."""
    alive = w.alive()
    workers = [p for p in alive if p.job is not None or p.trade]
    informal = [p for p in workers if p.trade or p.cash_job]
    return len(informal) / max(1, len(workers))


__all__ = ["Informal", "TRADES", "TRADE_WORDS", "informal_share"]
