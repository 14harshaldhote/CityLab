from collections import Counter

from citylab.core import lifecycle
from citylab.core.clock import MINUTES_PER_DAY, SimTime
from citylab.core.faith import FESTIVALS, PLACE_KINDS
from citylab.core.names import CITY_NAME, FAMILY
from citylab.core.people import WORSHIP
from citylab.core.world import World


def test_the_city_is_indian_with_a_place_for_every_faith():
    w = World(seed=2, population=300)
    city = w.city.to_dict()
    assert city["name"] == CITY_NAME
    assert "Kamal Chowk" in city["districts"]
    kinds = Counter(b.kind for b in w.city.buildings)
    for kind in PLACE_KINDS:
        assert kinds[kind] >= 1, kind
    assert kinds["temple"] >= 3
    names = [b.name for b in w.city.buildings]
    assert len(names) == len(set(names))


def test_families_share_a_faith_and_names_match_it(fresh_world):
    w = fresh_world
    for hh in w.households.values():
        faiths = {w.people[q].religion for q in hh.members}
        assert len(faiths) == 1  # founding households are one community
    for p in w.alive():
        if p.religion == "sikh":
            assert p.first.endswith(" Singh" if p.sex == "M" else " Kaur")
        if p.religion in FAMILY and not p.parents:
            assert p.last in FAMILY[p.religion]
        assert (p.devotion == 0) == (p.religion == "none")
    counts = Counter(p.religion for p in w.alive())
    assert counts.most_common(1)[0][0] == "hindu"
    assert counts["muslim"] > 0


def test_children_take_their_parents_faith(fresh_world):
    w = fresh_world
    mother = next(p for p in w.alive() if p.sex == "F" and p.partner is not None and 20 < p.age(0) < 40)
    father = w.people[mother.partner]
    baby = w.new_person(sex="M", born=w.t, household=mother.household, parents=(mother.id, father.id))
    assert baby.religion in (mother.religion, father.religion)


def test_people_worship_at_the_right_times(fresh_world):
    w = fresh_world
    seen: list[tuple[str, str, int]] = []
    start = w.brain._start

    def spy(p, activity, place, until, t):
        if activity == WORSHIP:
            seen.append((p.religion, w.city.buildings[place].kind, t))
        return start(p, activity, place, until, t)

    w.brain._start = spy
    money = w.economy.total()
    w.advance(7 * MINUTES_PER_DAY)  # Thursday 1 Jan to Thursday 8 Jan
    assert w.economy.total() == money  # offerings and langar move money, never make it
    assert seen
    where = {"hindu": "temple", "muslim": "mosque", "christian": "church", "sikh": "gurudwara", "buddhist": "vihara",
             "jain": "derasar", "parsi": "agiary"}
    for religion, kind, _ in seen:
        assert where[religion] == kind
    for _, _, t in seen:
        assert 5 <= SimTime(t).hour < 22  # nobody goes in the middle of the night
    church = [SimTime(t) for r, _, t in seen if r == "christian"]
    if church:
        assert Counter(s.weekday for s in church).most_common(1)[0][0] == 6  # Sunday Mass
    mosque = [SimTime(t) for r, _, t in seen if r == "muslim"]
    if mosque:
        assert Counter(s.weekday for s in mosque).most_common(1)[0][0] == 4  # Friday prayers


def test_festivals_are_announced(fresh_world):
    w = fresh_world
    heard = []
    w.bus.subscribe("festival", heard.append)
    day = min(FESTIVALS)
    w.t = day * MINUTES_PER_DAY
    lifecycle._festival(w)
    assert w.festival is not None and w.festival[1] == FESTIVALS[day][1]
    assert len(heard) == 1 and FESTIVALS[day][1] in heard[0].text
    assert w.summary()["festival"]["name"] == FESTIVALS[day][1]
