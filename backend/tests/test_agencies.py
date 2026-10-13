from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.world import World


def _crowded(seed=5, population=300):
    w = World(seed=seed, population=population)
    for b, occ in w.occupancy.items():
        w.city.buildings[b].households = len(occ)  # every home full
    return w


def test_departments_have_heads_and_bill_water():
    w = World(seed=5, population=300)
    money = w.economy.total()
    city = w.economy.balance["city"]
    w.advance(MINUTES_PER_DAY)
    view = w.government.view()
    heads = [d["head"] for d in view["departments"] if d["sector"] == "government"]
    assert any(h is not None for h in heads)  # led by staff of the municipal corporation
    assert len({h["id"] for h in heads if h}) == len([h for h in heads if h])  # one job each
    water = next(d for d in view["departments"] if d["key"] == "water")
    assert water["spent"] > 0 and "water" in water["watching"]
    assert abs(w.economy.total() - money) < 0.5
    assert w.economy.balance["city"] != city


def test_a_full_city_zones_land_lays_streets_and_builds_homes():
    w = _crowded()
    edges = w.city.graph.number_of_edges()
    version = w.city.version
    w.advance(MINUTES_PER_DAY * 2)
    assert w.government.roadworks, "Town Planning should have zoned a new block"
    assert w.city.roadworks
    w.advance(MINUTES_PER_DAY * 13)
    assert w.city.graph.number_of_edges() > edges  # the street graph grew
    sites = [b for b in w.city.buildings if b.status == "construction"]
    assert sites and all(b.kind == "home" for b in sites)
    assert w.city.version > version
    # a site is a workplace: its crew jobs are on offer
    assert any(bid == sites[0].id for bid, _ in w.vacancies())
    # and nobody can move in yet
    assert all(s.id not in w.occupancy for s in sites)


def test_finished_homes_are_sold_and_lived_in():
    w = _crowded()
    money = w.economy.total()
    w.advance(MINUTES_PER_DAY * 130)
    opened = [b for b in w.city.buildings if b.opened_day > 0 and b.kind == "home"]
    assert opened
    b = opened[0]
    assert b.status == "open" and b.households > 0 and b.id in w.occupancy
    assert not [l for l in w.economy.loans.values() if l.account == w.economy.company(b.id)]
    assert abs(w.economy.total() - money) < 0.5
    # people can reach the new streets
    other = w.city.buildings[0]
    assert w.router.distance(other, b) > 0


def test_new_schools_when_seats_run_out():
    w = World(seed=5, population=300)
    for b in w.city.buildings:
        if b.kind == "school":
            b.students = max(1, len(w.pupils[b.id]))
    w.advance(MINUTES_PER_DAY * 16)
    assert any(b.kind == "school" and b.status == "construction" for b in w.city.buildings) or w.government.roadworks
