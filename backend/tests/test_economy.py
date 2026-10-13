import pytest

from citylab.core import lifecycle
from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.world import World


def test_money_is_never_created_or_destroyed():
    w = World(seed=8, population=300)
    econ = w.economy
    assert econ.total() == pytest.approx(0.0, abs=0.01)  # every opening balance came from "outside"
    w.advance(10 * MINUTES_PER_DAY)
    assert econ.total() == pytest.approx(econ.total0, abs=0.5)
    assert len(w.daily) == 10 and w.daily[-1]["gdp"] > 0 and w.daily[-1]["tax"] > 0


def test_workers_are_paid_and_taxed(fresh_world):
    w = fresh_world
    worker = next(p for p in w.alive() if p.job and p.job.shift.weekdays_only)
    acct = w.economy.person(worker.id)
    w.economy.attendance[worker.job.building].append(worker.id)
    before, city = w.economy.balance[acct], w.economy.balance["city"]
    w.economy._wages()
    gross = worker.job.wage
    assert w.economy.balance[acct] == pytest.approx(before + gross * 0.85, abs=0.02)
    assert w.economy.balance["city"] > city


def test_shopping_needs_money(fresh_world):
    w = fresh_world
    p = next(q for q in w.alive() if q.age(0) >= 18)
    acct = w.economy.person(p.id)
    w.economy.transfer(acct, "outside", w.economy.balance[acct] - 10, "test")
    assert not w.economy.can_afford(p, 22)
    shop = w.city.of_kind("shop")[0].id
    w.economy.purchase(p, shop, 20.0, "shopping")
    assert w.economy.balance[acct] == pytest.approx(-10, abs=0.01)
    assert w.economy.balance[w.economy.company(shop)] > 0


def test_overdraft_becomes_a_loan_for_good_credit_and_is_repaid(fresh_world):
    w = fresh_world
    econ = w.economy
    p = next(q for q in w.alive() if q.age(0) >= 25)
    acct = econ.person(p.id)
    econ.credit[acct] = 720
    econ.transfer(acct, "outside", econ.balance[acct] + 500, "test")
    econ._bank()
    loan = next(l for l in econ.loans.values() if l.account == acct)
    assert econ.balance[acct] >= 0
    assert loan.principal == pytest.approx(800, abs=1)
    econ.transfer("outside", acct, 5000, "test")
    debt0 = loan.balance
    econ._bank()
    assert loan.balance < debt0
    # a full year of instalments clears it
    for _ in range(366):
        econ._bank()
    assert all(l.account != acct for l in econ.loans.values())


def test_bad_credit_falls_behind_and_defaults(fresh_world):
    w = fresh_world
    econ = w.economy
    p = next(q for q in w.alive() if q.age(0) >= 25)
    acct = econ.person(p.id)
    econ.credit[acct] = 700
    econ.transfer(acct, "outside", econ.balance[acct] + 2000, "test")
    econ._bank()  # gets a loan
    econ.transfer(acct, "outside", econ.balance[acct] + 10, "test")  # and spends it all
    for _ in range(61):
        econ._bank()
    assert all(l.account != acct for l in econ.loans.values())
    assert econ.credit[acct] < 600


def test_inheritance_goes_to_family(fresh_world):
    w = fresh_world
    econ = w.economy
    p = next(q for q in w.alive() if q.partner is not None)
    partner = p.partner
    money = econ.balance[econ.person(p.id)]
    before = econ.balance[econ.person(partner)]
    lifecycle._die(w, p)
    assert econ.balance[econ.person(p.id)] == 0
    assert econ.balance[econ.person(partner)] >= before + money * 0.99 / max(1, 1 + len([c for c in p.children if w.people[c].alive]))
