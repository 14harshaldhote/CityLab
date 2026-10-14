import pytest

from citylab.core import lifecycle
from citylab.core.clock import MINUTES_PER_DAY, MINUTES_PER_YEAR
from citylab.core.people import gompertz_annual
from citylab.core.realworld import LAST_WORKING_AGE
from citylab.core.world import World


class Always:
    """A stand-in random generator whose every draw succeeds."""

    def random(self, *a):
        return 0.0

    def integers(self, lo, hi=None, *a, **k):
        return 0 if hi is None else lo

    def poisson(self, lam):
        return max(1, int(lam))

    def uniform(self, lo, hi, *a):
        return lo

    def normal(self, mean, sd, *a):
        return mean

    def choice(self, n, *a, **k):
        return 0


def check_invariants(w: World) -> None:
    for hh in w.households.values():
        for q in hh.members:
            p = w.people[q]
            assert p.alive and p.household == hh.id
        if hh.members:
            assert hh.id in w.occupancy[hh.home]
    for b, occ in w.occupancy.items():
        assert len(occ) <= w.city.buildings[b].households
        assert all(w.households[h].members for h in occ)
    for p in w.alive():
        assert p.id in w.households[p.household].members
        if p.partner is not None:
            assert w.people[p.partner].partner == p.id and w.people[p.partner].alive
        if p.job is not None:
            assert p.id in w.job_holders[p.job.building]
        if p.school is not None:
            assert p.id in w.pupils[p.school]
    for b, holders in w.job_holders.items():
        assert len(holders) <= len(w.city.buildings[b].jobs)
        assert all(w.people[q].alive and w.people[q].job.building == b for q in holders)


def test_mortality_rises_with_age():
    assert gompertz_annual(20) < gompertz_annual(50) < gompertz_annual(80) < gompertz_annual(95)
    assert gompertz_annual(80) == pytest.approx(0.04, abs=0.015)
    assert gompertz_annual(70, health=0.3) > gompertz_annual(70, health=1.0)


def test_death_is_recorded_and_tidied(fresh_world):
    w = fresh_world
    p = next(q for q in w.alive() if q.partner is not None and q.job is not None)
    partner = p.partner
    lifecycle._die(w, p)
    assert not p.alive and p.died == w.t
    assert w.people[partner].partner is None
    assert p.id not in w.social.g
    assert w.today.deaths == 1
    check_invariants(w)


def test_couples_form_from_close_friends_and_move_in(fresh_world):
    w = fresh_world
    singles = [p for p in w.alive() if p.partner is None and 25 <= p.age(0) < 40]
    a = singles[0]
    b = next(q for q in singles[1:] if q.sex != a.sex and abs(q.age(0) - a.age(0)) < 10 and q.household != a.household)
    w.social.tie(a.id, b.id, "friend", 0.9)
    lifecycle._romance(w, Always(), [a])
    assert a.partner == b.id and b.partner == a.id
    assert a.household == b.household
    check_invariants(w)


def test_babies_are_born_into_the_family(fresh_world):
    w = fresh_world
    mother = next(p for p in w.alive() if p.sex == "F" and p.partner is not None and 20 <= p.age(0) < 35)
    before = len(mother.children)
    lifecycle._births(w, Always(), [mother])
    baby = w.people[mother.children[-1]]
    assert len(mother.children) == before + 1
    assert set(baby.parents) == {mother.id, mother.partner}
    assert baby.household == mother.household and baby.age(w.t) == 0
    assert w.social.g.edges[baby.id, mother.id]["kind"] == "parent"
    check_invariants(w)


def test_birthdays_move_people_through_life(fresh_world):
    w = fresh_world
    w.advance(MINUTES_PER_DAY)  # now at midnight of day 1
    kid = next(p for p in w.alive() if p.age(0) < 3 and p.school is None)
    kid.born = w.t - 6 * MINUTES_PER_YEAR
    teen = next(p for p in w.alive() if p.school is not None)
    teen.born = w.t - 18 * MINUTES_PER_YEAR
    worker = next(p for p in w.alive() if p.job is not None and not p.retired)
    worker.born = w.t - LAST_WORKING_AGE * MINUTES_PER_YEAR
    for p in (kid, teen, worker):
        lifecycle._birthday(w, p, w.t)
    assert kid.school is not None
    # at 18 most go looking for work and the rest go on to college, as in PLFS
    assert teen.school is None and (teen.unemployed_since == w.t) != teen.at_home
    assert worker.retired and worker.job is None
    check_invariants(w)


def test_job_seekers_get_hired(fresh_world):
    w = fresh_world
    seeker = next(p for p in w.alive() if 25 <= p.age(0) < 60 and p.job is not None)
    w.fire(seeker)
    lifecycle._jobs(w, Always(), [seeker])
    assert seeker.job is not None and seeker.unemployed_since is None
    check_invariants(w)


def test_open_jobs_pull_newcomers(fresh_world):
    w = fresh_world
    before = len(w.alive())
    lifecycle._migration(w, Always())
    assert len(w.alive()) > before
    assert w.today.arrived == len(w.alive()) - before
    check_invariants(w)


def test_two_months_of_life_keep_the_city_consistent():
    w = World(seed=6, population=300)
    w.advance(60 * MINUTES_PER_DAY)
    check_invariants(w)
    assert len(w.daily) == 60
    assert w.bus.count > 60
    pop = [r["population"] for r in w.daily]
    assert 0.8 * pop[0] < pop[-1] < 1.5 * pop[0]
