"""Money: the bank, companies, the city budget and every household's wallet.

Every unit of money lives in exactly one account, and money only ever moves with a
double-entry ``transfer``: what leaves one account enters another. The total across
all accounts therefore never changes, which the tests check to the last paisa, just
as LotusLab's water ledger closed its mass balance. Money enters and leaves the city
through one account, ``outside`` (the rest of the world): it buys what offices and
factories make, sells shops their stock and takes landlords' upkeep.

Accounts are keyed by short strings: ``p:<person>``, ``c:<building>`` (every
workplace is a company or a public service), ``city``, ``bank``, ``landlord`` and
``outside``.

Once a day (``end_of_day``):

1. **Wages** for everyone who worked a shift, paid by their company (or by the city
   for schools, the hospital, police, City Hall and parks), with income tax withheld.
2. **Sales**: offices, factories and the bus depot sell their output to the outside
   world, in proportion to who turned up and how skilled they are.
3. **Living costs**: each household pays rent to the landlord and buys groceries
   from its nearest shop (with sales tax). Meals out and shopping trips are paid on
   the spot, during the day.
4. **Welfare**: pensions for the retired and benefits for job seekers, paid by the city.
5. **The bank** pays interest on savings, collects loan instalments, turns
   overdrafts into loans for people and companies it trusts, and records missed
   payments for those it does not.
6. **Places of worship** are trusts: they live on visitors' offerings, pay their
   priests and caretakers, and spend what is left on festivals, upkeep and charity.
   The gurudwara's free kitchen (langar) feeds everyone who comes.
7. **Companies** that run out of money borrow or lay people off.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from .clock import DAYS_PER_YEAR, MINUTES_PER_DAY

if TYPE_CHECKING:
    from .people import Person
    from .world import World

PUBLIC = ("school", "hospital", "police", "city_hall", "park", "court")
TRUSTS = ("temple", "mosque", "church", "gurudwara", "vihara", "derasar", "agiary")  # run on offerings, pay no tax or dividends
OWN_PAYER = {"bank": "bank"}  # City Bank pays its own staff from its own account
EXPORTERS = ("office", "factory", "bus_depot")
RETAIL = ("shop", "restaurant")

SALES_TAX = 0.05
BUSINESS_TAX = 0.05  # of a company's revenue
PROPERTY_TAX = 0.10  # of rent collected
DIVIDEND_SHARE = 0.25  # of cash above a cushion of 30 days' wages, paid to outside shareholders
PENSION_PER_DAY = 60.0
BENEFIT_DAYS = 180
GROCERIES_PER_PERSON = 14.0
RENT_PER_DAY = {"apartment": 45.0, "house": 70.0}
MEAL_OUT = 22.0
WHOLESALE_SHARE = 0.4  # what a shop pays the outside world for the goods it sells
UPKEEP_SHARE = 0.35  # what the landlord spends on upkeep
OUTPUT_PER_WAGE = 1.4
LANGAR_MEAL = 8.0  # what the gurudwara's free kitchen spends per meal  # how much an average worker's day sells for, relative to their wage


@dataclass(slots=True)
class Loan:
    id: int
    account: str
    principal: float
    rate: float  # annual
    days: int
    balance: float
    instalment: float
    opened: int  # sim minute
    missed: int = 0
    purpose: str = ""


class Economy:
    def __init__(self, world: World) -> None:
        self.w = world
        self.rng = world.streams("economy")
        self.balance: dict[str, float] = defaultdict(float)
        self.credit: dict[str, float] = {}
        self.loans: dict[int, Loan] = {}
        self._next_loan = 0
        self.base_rate = 0.06
        self.attendance: dict[int, list[int]] = defaultdict(list)  # building -> people who worked today
        self.flows: dict[str, float] = defaultdict(float)  # today's money flows by purpose
        self.company_sales: dict[int, float] = defaultdict(float)  # today's revenue by building
        self.history: dict[str, list[float]] = defaultdict(list)
        self.total0 = 0.0

    # ---- accounts -------------------------------------------------------------------

    @staticmethod
    def person(pid: int) -> str:
        return f"p:{pid}"

    @staticmethod
    def company(bid: int) -> str:
        return f"c:{bid}"

    def payer_for(self, bid: int) -> str:
        """Who pays a workplace's wages: the company itself, or the city for public services."""
        kind = self.w.city.buildings[bid].kind
        return "city" if kind in PUBLIC else OWN_PAYER.get(kind, self.company(bid))

    def transfer(self, src: str, dst: str, amount: float, purpose: str) -> float:
        amount = round(float(amount), 2)
        if amount <= 0 or src == dst:
            return 0.0
        self.balance[src] = round(self.balance[src] - amount, 2)
        self.balance[dst] = round(self.balance[dst] + amount, 2)
        self.flows[purpose] += amount
        return amount

    def total(self) -> float:
        return round(sum(self.balance.values()), 2)

    def found(self) -> None:
        """Opening balances for the founding city. Called once, after the first people exist."""
        rng = self.rng
        self.balance["outside"] = 0.0
        self._seed("bank", 1_500_000.0)
        self._seed("city", 400_000.0)
        self._seed("landlord", 100_000.0)
        for b in self.w.city.buildings:
            if b.jobs and b.kind not in PUBLIC and b.kind not in OWN_PAYER:
                self._seed(self.company(b.id), 3000.0 * len(b.jobs) * float(rng.uniform(0.6, 1.4)))
                self.credit[self.company(b.id)] = 650.0
        for p in self.w.alive():
            self.open(p, founding=True)
        self.total0 = self.total()

    def _seed(self, account: str, amount: float) -> None:
        # opening money comes from outside, so the books balance from minute one
        self.transfer("outside", account, amount, "opening balances")

    def open(self, p: Person, founding: bool = False) -> None:
        acct = self.person(p.id)
        self.credit[acct] = float(np.clip(self.rng.normal(650, 60), 450, 800))
        age = p.age(self.w.t)
        if age >= 18:
            days = float(self.rng.lognormal(math.log(25.0), 0.8)) * (1.6 if age >= 40 else 1.0)
            self._seed(acct, round(days * 110.0, 2))  # savings worth some weeks of wages
        elif founding and age >= 12:
            self._seed(acct, round(float(self.rng.uniform(0, 300)), 2))

    def close(self, p: Person, reason: str) -> None:
        """A person died or left: their money goes to family (or leaves with them), their loans are settled."""
        acct = self.person(p.id)
        for loan in [l for l in self.loans.values() if l.account == acct]:
            pay = min(max(0.0, self.balance[acct]), loan.balance)
            self.transfer(acct, "bank", pay, "loan repayments")
            loan.balance -= pay
            if loan.balance > 0.01:
                self._default(loan)
            else:
                del self.loans[loan.id]
        left = self.balance[acct]
        if reason == "left":
            heirs: list[int] = []
            dst = "outside"
        else:
            heirs = [q for q in ([p.partner] if p.partner is not None else []) + p.children if q in self.w.people and self.w.people[q].alive]
            dst = "city"
        if left > 0:
            if heirs:
                for k, q in enumerate(heirs):  # the last heir takes what rounding left over
                    share = self.balance[acct] if k == len(heirs) - 1 else left / len(heirs)
                    self.transfer(acct, self.person(q), share, "inheritance")
            else:
                self.transfer(acct, dst, left, "inheritance" if dst == "city" else "money leaving the city")
        elif left < 0:
            self.transfer("bank", acct, -left, "bad debt written off")

    # ---- spending during the day ------------------------------------------------------

    def can_afford(self, p: Person, price: float) -> bool:
        return self.balance[self.person(p.id)] >= price + 50.0

    def purchase(self, p: Person, bid: int, amount: float, purpose: str) -> None:
        """A sale at a shop or restaurant, with sales tax to the city."""
        acct = self.person(p.id)
        tax = round(amount * SALES_TAX, 2)
        self.transfer(acct, self.company(bid), amount - tax, purpose)
        self.transfer(acct, "city", tax, "sales tax")
        self.company_sales[bid] += amount - tax

    def offering(self, p: Person, bid: int) -> None:
        """A voluntary offering (dakshina, sadaqah, collection) from adults who can spare it."""
        if p.age(self.w.t) < 18 or not self.can_afford(p, 60.0):
            return
        amount = float(self.rng.uniform(5, 25)) * (0.5 + p.devotion)
        self.transfer(self.person(p.id), self.company(bid), amount, "offerings")

    def langar(self, bid: int) -> None:
        self.transfer(self.company(bid), "outside", LANGAR_MEAL, "langar kitchen")

    def meal_price(self) -> float:
        return MEAL_OUT

    def shopping_price(self) -> float:
        return round(float(self.rng.uniform(15, 60)), 2)

    # ---- the daily cycle ----------------------------------------------------------------

    def end_of_day(self) -> dict[str, Any]:
        w = self.w
        t = w.t
        self._wages()
        self._exports()
        self._households()
        self._welfare()
        self._retail_costs()
        self._business_tax_and_dividends()
        self._landlord()
        self._bank()
        self._companies()
        if self.balance["city"] < 0:
            self._borrow("city", -self.balance["city"] + 50_000.0, "to cover the city budget")
        summary = self.summary()
        for k in ("money_people", "money_companies", "city", "loans_outstanding", "gdp"):
            self.history[k].append(summary[k])
        self.attendance = defaultdict(list)
        self.company_sales = defaultdict(float)
        self.flows = defaultdict(float)
        assert abs(self.total() - self.total0) < 0.5, f"money leaked: {self.total() - self.total0} at {t}"
        return summary

    def _wages(self) -> None:
        w = self.w
        for bid in sorted(self.attendance):
            payer = self.payer_for(bid)
            for pid in self.attendance[bid]:
                p = w.people.get(pid)
                if p is None or p.job is None or p.job.building != bid:
                    continue
                gross = p.job.wage
                tax = round(gross * self.w.policy.income_tax, 2)
                self.transfer(payer, self.person(pid), gross - tax, "wages")
                self.transfer(payer, "city", tax, "income tax")

    def _exports(self) -> None:
        w = self.w
        for bid in sorted(self.attendance):
            b = w.city.buildings[bid]
            if b.kind not in EXPORTERS or b.status != "open":
                continue
            value = 0.0
            for pid in self.attendance[bid]:
                p = w.people.get(pid)
                if p is not None and p.job is not None:
                    value += p.job.wage * OUTPUT_PER_WAGE * (0.75 + 0.5 * p.skill) * float(self.rng.uniform(0.85, 1.15))
            self.transfer("outside", self.company(bid), value, "sales to the outside world")
            self.company_sales[bid] += value

    def _households(self) -> None:
        w = self.w
        for hh in w.households.values():
            if not hh.members:
                continue
            home = w.city.buildings[hh.home]
            rent = RENT_PER_DAY["apartment" if home.households > 3 else "house"]
            self._household_pays(hh.members, "landlord", rent, "rent")
            shops = w._nearby(hh.home, "shop")
            payer = self._richest_adult(hh.members)
            if shops and payer is not None:
                self.purchase(w.people[payer], shops[0].id, GROCERIES_PER_PERSON * len(hh.members), "groceries")

    def _household_pays(self, members: list[int], dst: str, amount: float, purpose: str) -> None:
        """Adults share a bill in proportion to what they have; if they cannot, it overdraws the richest."""
        adults = [q for q in members if self.w.people[q].age(self.w.t) >= 18]
        if not adults:
            adults = members
        pos = {q: max(0.0, self.balance[self.person(q)]) for q in adults}
        total = sum(pos.values())
        if total <= 0:
            self.transfer(self.person(self._richest_adult(members) or adults[0]), dst, amount, purpose)
            return
        for q in adults:
            self.transfer(self.person(q), dst, amount * pos[q] / total, purpose)

    def _richest_adult(self, members: list[int]) -> int | None:
        adults = [q for q in members if self.w.people[q].age(self.w.t) >= 18] or members
        return max(adults, key=lambda q: (self.balance[self.person(q)], -q)) if adults else None

    def _welfare(self) -> None:
        w = self.w
        for p in w.alive():
            if p.retired:
                self.transfer("city", self.person(p.id), PENSION_PER_DAY, "pensions")
            elif p.unemployed_since is not None and p.job is None and w.t - p.unemployed_since < BENEFIT_DAYS * MINUTES_PER_DAY:
                self.transfer("city", self.person(p.id), self.w.policy.benefit, "unemployment benefit")

    def _retail_costs(self) -> None:
        for bid in sorted(self.company_sales):
            if self.w.city.buildings[bid].kind in RETAIL:
                self.transfer(self.company(bid), "outside", self.company_sales[bid] * WHOLESALE_SHARE, "wholesale stock")

    def _landlord(self) -> None:
        rent = self.flows.get("rent", 0.0)
        self.transfer("landlord", "outside", rent * UPKEEP_SHARE, "building upkeep")
        self.transfer("landlord", "city", rent * PROPERTY_TAX, "property tax")

    def _business_tax_and_dividends(self) -> None:
        w = self.w
        for bid in sorted(self.company_sales):
            self.transfer(self.company(bid), "city", self.company_sales[bid] * BUSINESS_TAX, "business tax")
        for bid, holders in sorted(w.job_holders.items()):
            b = w.city.buildings[bid]
            if b.kind in PUBLIC or b.kind in OWN_PAYER or b.status != "open":
                continue
            acct = self.company(bid)
            cushion = 30 * sum(w.people[q].job.wage for q in holders if w.people[q].job) + 5000.0
            if self.balance[acct] > cushion:
                purpose = "festivals, upkeep and charity" if b.kind in TRUSTS else "dividends"
                self.transfer(acct, "outside", (self.balance[acct] - cushion) * DIVIDEND_SHARE, purpose)

    # ---- the bank ------------------------------------------------------------------------------

    @property
    def savings_rate(self) -> float:
        return max(0.0, self.base_rate - 0.03)

    def loan_rate(self, account: str) -> float:
        score = self.credit.get(account, 650.0)
        return round(self.base_rate + 0.03 + max(0.0, (700.0 - score) / 100.0) * 0.04, 4)

    def _bank(self) -> None:
        w = self.w
        r = self.savings_rate / DAYS_PER_YEAR
        for acct in sorted(self.balance):
            if acct.startswith(("p:", "c:")) and self.balance[acct] > 0:
                self.transfer("bank", acct, self.balance[acct] * r, "interest on savings")
        for loan in list(self.loans.values()):
            interest = loan.balance * loan.rate / DAYS_PER_YEAR
            loan.balance += interest
            due = min(loan.instalment, loan.balance)
            if self.balance[loan.account] >= due:
                self.transfer(loan.account, "bank", due, "loan repayments")
                loan.balance -= due
                self.credit[loan.account] = min(850.0, self.credit.get(loan.account, 600.0) + 0.2)
            else:
                loan.missed += 1
                self.credit[loan.account] = max(300.0, self.credit.get(loan.account, 600.0) - 4.0)
                if loan.missed >= 60:
                    self._default(loan)
                    continue
            if loan.balance <= 0.01:
                del self.loans[loan.id]
        # overdrafts: the bank lends to those it trusts, the rest fall behind
        for acct in sorted(self.balance):
            if not acct.startswith(("p:", "c:")) or self.balance[acct] >= 0:
                continue
            if acct.startswith("p:"):
                pid = int(acct[2:])
                if pid not in w.people or not w.people[pid].alive:
                    continue
            need = -self.balance[acct] + 300.0
            behind = any(l.missed for l in self.loans.values() if l.account == acct)
            if not behind and self.credit.get(acct, 600.0) >= 560.0 and self._debt(acct) < 20_000.0:
                self._borrow(acct, need, "to cover an overdraft")
            else:
                self.credit[acct] = max(300.0, self.credit.get(acct, 600.0) - 2.0)

    def _debt(self, account: str) -> float:
        return sum(l.balance for l in self.loans.values() if l.account == account)

    def _borrow(self, account: str, amount: float, purpose: str, days: int = 365) -> Loan:
        rate = self.loan_rate(account) if account != "city" else self.base_rate + 0.01
        i = rate / DAYS_PER_YEAR
        instalment = amount * i / (1 - (1 + i) ** -days)
        loan = Loan(self._next_loan, account, round(amount, 2), rate, days, amount, round(instalment, 2), self.w.t, purpose=purpose)
        self._next_loan += 1
        self.loans[loan.id] = loan
        self.transfer("bank", account, amount, "loans issued")
        who = self.describe(account)
        people = (int(account[2:]),) if account.startswith("p:") else ()
        place = int(account[2:]) if account.startswith("c:") else None
        self.w.emit("loan", f"{who} borrowed {amount:,.0f} from City Bank at {rate * 100:.1f}% {purpose}.", people, place,
                    amount=round(amount, 2), rate=rate, account=account)
        return loan

    def _default(self, loan: Loan) -> None:
        del self.loans[loan.id]
        self.credit[loan.account] = max(300.0, self.credit.get(loan.account, 600.0) - 150.0)
        people = (int(loan.account[2:]),) if loan.account.startswith("p:") else ()
        self.w.emit("default", f"{self.describe(loan.account)} defaulted on a loan; City Bank wrote off {loan.balance:,.0f}.", people,
                    amount=round(loan.balance, 2))

    def describe(self, account: str) -> str:
        if account.startswith("p:"):
            return self.w.people[int(account[2:])].name
        if account.startswith("c:"):
            return self.w.city.buildings[int(account[2:])].name
        return {"city": "The city", "bank": "City Bank", "landlord": "The landlord", "outside": "The outside world"}.get(account, account)

    # ---- companies --------------------------------------------------------------------------------

    def _companies(self) -> None:
        w = self.w
        for bid, holders in sorted(w.job_holders.items()):
            b = w.city.buildings[bid]
            if b.kind in PUBLIC or b.kind in OWN_PAYER or not holders or b.status != "open":
                continue
            acct = self.company(bid)
            if self.balance[acct] >= 0:
                continue
            # still short after the bank had its say: cut costs
            if self.rng.random() < 0.5:
                pid = max(holders, key=lambda q: (w.t - w.people[q].job.since, q)) if self.rng.random() < 0.3 else holders[-1]
                p = w.people[pid]
                w.fire(p)
                p.unemployed_since = w.t
                w.emit("laid_off", f"{b.name} laid off {p.name} to cut costs.", (pid,), bid)

    # ---- views -----------------------------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        people = [v for k, v in self.balance.items() if k.startswith("p:") and self._alive(k)]
        companies = [v for k, v in self.balance.items() if k.startswith("c:")]
        flows = dict(self.flows)
        gdp = flows.get("wages", 0) + flows.get("income tax", 0)
        return {
            "money_people": round(sum(people), 2),
            "money_companies": round(sum(companies), 2),
            "median_balance": round(float(np.median(people)), 2) if people else 0.0,
            "in_debt": sum(1 for v in people if v < 0),
            "city": round(self.balance["city"], 2),
            "bank": round(self.balance["bank"], 2),
            "landlord": round(self.balance["landlord"], 2),
            "loans_outstanding": round(sum(l.balance for l in self.loans.values()), 2),
            "loans": len(self.loans),
            "base_rate": self.base_rate,
            "savings_rate": self.savings_rate,
            "gdp": round(gdp, 2),
            "tax": round(sum(v for k, v in flows.items() if k.endswith("tax")), 2),
            "flows": {k: round(v, 2) for k, v in sorted(flows.items(), key=lambda kv: -kv[1])},
        }

    def _alive(self, acct: str) -> bool:
        p = self.w.people.get(int(acct[2:]))
        return p is not None and p.alive

    def person_view(self, pid: int) -> dict[str, Any]:
        acct = self.person(pid)
        loans = [l for l in self.loans.values() if l.account == acct]
        return {
            "balance": round(self.balance[acct], 2),
            "credit_score": round(self.credit.get(acct, 0.0)),
            "debt": round(sum(l.balance for l in loans), 2),
            "loans": [{"balance": round(l.balance, 2), "rate": l.rate, "instalment": l.instalment, "missed": l.missed} for l in loans],
        }

    def company_view(self, bid: int) -> dict[str, Any] | None:
        b = self.w.city.buildings[bid]
        if not b.jobs:
            return None
        if b.kind in PUBLIC:
            return {"public": True, "funded_by": "city"}
        if b.kind in OWN_PAYER:
            return {"public": False, "funded_by": OWN_PAYER[b.kind], "balance": round(self.balance[OWN_PAYER[b.kind]], 2)}
        acct = self.company(bid)
        return {"public": False, "balance": round(self.balance[acct], 2), "credit_score": round(self.credit.get(acct, 0)),
                "debt": round(self._debt(acct), 2)}

    def companies(self) -> list[dict[str, Any]]:
        out = []
        for b in self.w.city.buildings:
            if b.jobs and b.kind not in PUBLIC and b.kind not in OWN_PAYER and b.status == "open":
                acct = self.company(b.id)
                out.append({"id": b.id, "name": b.name, "kind": b.kind, "balance": round(self.balance[acct], 2),
                            "workers": len(self.w.job_holders.get(b.id, [])), "jobs": len(b.jobs), "debt": round(self._debt(acct), 2)})
        out.sort(key=lambda c: -c["balance"])
        return out
