import hashlib
import json

from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.people import (
    EAT_HOME, SCHOOL, SLEEP, TRAVEL, WORK, Person, urgency,
)
from citylab.core.world import World


def _at(world: World, day: int, hour: float) -> None:
    world.advance(day * MINUTES_PER_DAY + int(hour * 60) - world.t)


def test_needs_drain_and_activities_restore_them():
    p = Person(id=0, first="A", last="B", sex="F", born=-30 * 525600, household=0,
               openness=.5, conscientiousness=.5, extraversion=.5, agreeableness=.5, neuroticism=.5)
    p.hunger = p.energy = 1.0
    p.activity, p.needs_t = WORK, 0
    p.update_needs(6 * 60)
    assert p.hunger < 0.1 and 0.6 < p.energy < 0.85
    p.activity = EAT_HOME
    p.update_needs(6 * 60 + 30)
    assert p.hunger > 0.9
    p.activity = SLEEP
    before = p.energy
    p.update_needs(6 * 60 + 30 + 8 * 60)
    assert p.energy == 1.0 > before
    assert urgency(0.1) > urgency(0.5) > urgency(0.9) >= 0


def test_founding_population_is_a_plausible_town(fresh_world):
    w = fresh_world
    s = w.summary()
    assert 380 <= s["population"] <= 420
    ages = [p.age(0) for p in w.alive()]
    assert min(ages) >= 0 and max(ages) < 100
    assert sum(a < 18 for a in ages) > 0.12 * len(ages)
    assert s["employed"] > 0.7 * (s["employed"] + s["unemployed"])
    for p in w.alive():
        if p.partner is not None:
            assert w.people[p.partner].partner == p.id
        for c in p.children:
            assert p.id in w.people[c].parents


def test_a_weekday_has_a_rhythm(fresh_world):
    w = fresh_world
    _at(w, 4, 3)  # Monday 03:00
    asleep = sum(p.activity == SLEEP for p in w.alive()) / len(w.alive())
    assert asleep > 0.85
    _at(w, 4, 11)  # Monday 11:00
    alive = w.alive()
    workers = [p for p in alive if p.job and p.job.shift.weekdays_only]
    at_work = sum(p.activity in (WORK, TRAVEL) and (p.place == p.job.building or p.pending and p.pending.place == p.job.building) for p in workers)
    assert at_work > 0.8 * len(workers)
    pupils = [p for p in alive if p.school is not None]
    assert sum(p.activity == SCHOOL for p in pupils) > 0.8 * len(pupils)


def test_trips_move_people_along_streets(fresh_world):
    w = fresh_world
    _at(w, 4, 8)
    movers = [p for p in w.alive() if p.activity == TRAVEL]
    assert movers
    p = movers[0]
    x0, y0 = w.position(p)
    w.advance(1)
    if p.activity == TRAVEL:
        assert w.position(p) != (x0, y0)


def test_same_seed_same_day():
    def fingerprint(world: World) -> str:
        world.advance(MINUTES_PER_DAY + 9 * 60)
        f = world.frame()
        return hashlib.sha256(json.dumps([f["x"], f["y"], f["activity"]]).encode()).hexdigest()

    assert fingerprint(World(seed=9, population=150)) == fingerprint(World(seed=9, population=150))


def test_friendships_grow_from_shared_places(fresh_world):
    w = fresh_world
    before = w.social.summary()["friendships"]
    w.advance(3 * MINUTES_PER_DAY)
    assert len(w.daily) == 3
    assert sum(r["new_friendships"] for r in w.daily) > 0
    assert w.social.summary()["friendships"] > 0.5 * before
