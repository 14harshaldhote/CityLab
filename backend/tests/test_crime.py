import copy
import math

from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.crime import CAMERA_RANGE, Case, temptation
from citylab.core.people import JAIL
from citylab.core.world import World


def _adult(w: World):
    return next(p for p in sorted(w.alive(), key=lambda p: p.id) if 25 <= p.age(w.t) < 50)


def test_temptation_comes_from_hard_times_not_from_who_you_are():
    w = World(seed=7, population=200)
    p = _adult(w)
    p.conscientiousness = p.agreeableness = 0.2
    comfortable = temptation(p, 20_000, 0, w.t)
    w.fire(p)
    broke = temptation(p, 50, 3000, w.t)
    assert broke > 5 * comfortable
    # the same person with another faith, name or home is exactly as tempted
    other = copy.copy(p)
    other.religion, other.first, other.last, other.household = "parsi", "Zubin", "Irani", -1
    assert temptation(other, 50, 3000, w.t) == broke
    child = next(q for q in w.alive() if q.age(w.t) < 12)
    assert temptation(child, 0, 9000, w.t) == 0.0


def test_the_city_has_a_court_police_departments_and_cameras():
    w = World(seed=7, population=400)
    assert [b.name for b in w.city.buildings if b.kind == "court"] == ["Kamalnagar District Court"]
    assert len(w.crime.cameras) == 5
    w.advance(MINUTES_PER_DAY + 12 * 60)
    keys = {d["key"]: d for d in w.government.view()["departments"]}
    assert "police" in keys and "court" in keys
    assert w.crime.patrols, "officers on duty go out on patrol"
    frame = w.frame()
    assert all(len(pc) == 4 for pc in frame["police"]) and "crimes" in frame


def _theft(w: World, kind="burglary", evidence=0.95) -> Case:
    cr = w.crime
    thief, victim = [p for p in sorted(w.alive(), key=lambda p: p.id) if 25 <= p.age(w.t) < 50][:2]
    econ = w.economy
    econ.transfer("outside", econ.person(victim.id), 5000, "test savings")
    home = w.city.buildings[w.households[victim.household].home]
    cr.patrols = []  # nobody around to stop it
    cr._commit(thief, kind, w.t, home.x, home.y, home.name, home.id, econ.person(victim.id), victim.id, victim.name, 1200.0, [])
    c = cr.cases[max(cr.cases)]
    c.reported, c.status, c.evidence = True, "investigating", evidence
    return c


def test_a_burglary_is_investigated_tried_and_punished():
    w = World(seed=7, population=400)
    w.advance(MINUTES_PER_DAY + 9 * 60)  # Friday morning
    econ = w.economy
    money = econ.total()
    c = _theft(w)
    thief = w.people[c.offender]
    thief_before = econ.balance[econ.person(thief.id)]
    assert econ.flows["stolen"] == 1200.0
    for _ in range(40):
        if c.status != "investigating":
            break
        w.crime._investigate(w.t)
    assert c.status == "awaiting trial" and c.hearing_day is not None
    assert (c.hearing_day + 3) % 7 < 5  # the court sits on weekdays
    w.crime.rng = __import__("numpy").random.default_rng(0)  # strong evidence: guilty
    c.hearing_day = w.t // MINUTES_PER_DAY
    city = econ.balance["city"]
    w.crime._hearings(w.t)
    assert c.status == "convicted" and thief.record == 1
    assert econ.balance["city"] > city  # the fine
    assert econ.balance[econ.person(thief.id)] < thief_before
    assert thief.activity == JAIL and thief.jailed_until > w.t
    assert w.city.buildings[thief.place].kind == "police"
    assert abs(econ.total() - money) < 0.5  # every rupee is accounted for
    w.advance(19 * MINUTES_PER_DAY)
    assert thief.jailed_until <= w.t and thief.activity != JAIL


def test_patrols_put_thieves_off_and_catch_some_in_the_act():
    w = World(seed=7, population=400)
    w.advance(MINUTES_PER_DAY + 9 * 60)
    cr = w.crime
    thief = _adult(w)
    shop = next(b for b in w.city.buildings if b.kind == "shop")
    cr.w.crime._patrol(w.t - w.t % 30)
    pa = cr.patrols[0]
    from citylab.core.routing import Trip

    pa.trip = Trip(depart=w.t, arrive=w.t + 600, points=[(shop.x, shop.y)] * 2, times=[w.t, w.t + 600.0], legs=[2], mode="car")
    cr.patrols = [pa]
    before = len(cr.cases)
    for _ in range(60):
        cr._commit(thief, "shoplift", w.t, shop.x, shop.y, shop.name, shop.id, w.economy.company(shop.id), None, shop.name, 300.0, [])
    new = [c for c in cr.cases.values() if c.id > before]
    assert cr.today.deterred > 20
    assert any(c.caught for c in new)


def test_police_put_a_camera_where_thefts_keep_happening():
    w = World(seed=7, population=200)
    w.economy.transfer("outside", "city", 500_000, "test grant")
    cr = w.crime
    node = next(n for n in sorted(w.city.graph.nodes) if cr.covered(*w.city.node_xy(n)) is None)
    x, y = w.city.node_xy(node)
    for k in range(4):
        cr._case_id += 1
        cr.cases[cr._case_id] = Case(cr._case_id, "pickpocket", w.t, x + 10 * k, y, "a corner", None, "outside", None, "someone", 100.0, 0)
    version = w.city.version
    cr._plan_cameras()
    assert len(cr.cameras) == 6 and w.city.version > version
    assert math.dist(w.city.node_xy(cr.cameras[-1]), (x, y)) <= CAMERA_RANGE * 1.2
