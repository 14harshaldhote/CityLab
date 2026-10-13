"""Citizens, their households and the needs that drive them.

A person carries four needs between 0 (desperate) and 1 (fully satisfied): hunger,
energy, social and fun. Needs drain at a base rate and every activity adds its own
effect (sleep restores energy, a meal restores hunger, a visit restores social).
Needs are updated lazily: only when the person next makes a decision do we apply
``rate x minutes elapsed`` for the activity they were doing. That is exact (rates are
constant within an activity) and costs nothing while they sleep through the night.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .citygen import Shift
from .clock import MINUTES_PER_YEAR
from .routing import Trip

NEEDS = ("hunger", "energy", "social", "fun")

# activity codes, shared with the frontend (index = colour/legend)
SLEEP, HOME, EAT_HOME, EAT_OUT, WORK, SCHOOL, SOCIAL, PARK, SHOP, TRAVEL = range(10)
ACTIVITY_NAMES = ("sleeping", "at home", "eating at home", "eating out", "working", "at school", "visiting friends", "at the park", "shopping", "travelling")

# per-minute base drain, then per-activity additions (hunger, energy, social, fun)
BASE_RATE = (-1 / 360, -1 / 1400, -1 / 1800, -1 / 800)
ACTIVITY_RATE: dict[int, tuple[float, float, float, float]] = {
    SLEEP: (1 / 720, 1 / 640 + 1 / 1400, 1 / 3600, 1 / 1600),
    HOME: (0.0, 1 / 2500, 1 / 3000, 1 / 220),
    EAT_HOME: (1 / 25, 0.0, 1 / 2000, 1 / 1000),
    EAT_OUT: (1 / 25, 0.0, 1 / 150, 1 / 200),
    WORK: (0.0, 0.0, 1 / 1200, -1 / 1500),
    SCHOOL: (0.0, 0.0, 1 / 500, 0.0),
    SOCIAL: (0.0, 0.0, 1 / 80, 1 / 300),
    PARK: (0.0, 0.0, 1 / 400, 1 / 90),
    SHOP: (0.0, 0.0, 1 / 800, 1 / 150),
    TRAVEL: (0.0, 0.0, 0.0, 0.0),
}


@dataclass(slots=True)
class Job:
    building: int
    shift: Shift
    wage: float
    since: int


@dataclass(slots=True)
class Plan:
    """What a person will do once they arrive."""

    activity: int
    place: int
    until: int


@dataclass(slots=True)
class Person:
    id: int
    first: str
    last: str
    sex: str  # "F" | "M"
    born: int  # sim minute of birth (negative for the founding population)
    household: int
    # Big Five personality, each 0..1
    openness: float
    conscientiousness: float
    extraversion: float
    agreeableness: float
    neuroticism: float
    parents: tuple[int, ...] = ()
    children: list[int] = field(default_factory=list)
    partner: int | None = None
    job: Job | None = None
    school: int | None = None
    retired: bool = False
    unemployed_since: int | None = None
    skill: float = 0.3
    health: float = 1.0
    alive: bool = True
    died: int | None = None
    arrived: int = 0  # sim minute they joined the city (born or moved in)
    # needs and current activity
    hunger: float = 0.8
    energy: float = 0.8
    social: float = 0.6
    fun: float = 0.6
    needs_t: int = 0
    activity: int = HOME
    place: int | None = None  # building id, None while travelling
    until: int = 0
    trip: Trip | None = None
    pending: Plan | None = None
    last_shift: int = -1  # absolute start minute of the last shift worked
    last_school_day: int = -1

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}"

    def age(self, t: int) -> float:
        return (t - self.born) / MINUTES_PER_YEAR

    def update_needs(self, t: int) -> None:
        dt = t - self.needs_t
        if dt <= 0:
            return
        add = ACTIVITY_RATE[self.activity]
        self.hunger = _clamp(self.hunger + (BASE_RATE[0] + add[0]) * dt)
        self.energy = _clamp(self.energy + (BASE_RATE[1] + add[1]) * dt)
        self.social = _clamp(self.social + (BASE_RATE[2] + add[2]) * dt)
        self.fun = _clamp(self.fun + (BASE_RATE[3] + add[3]) * dt)
        self.needs_t = t

    @property
    def mood(self) -> float:
        """0..1, the weakest needs weigh most (a starving person is not happy because they had fun)."""
        vals = sorted((self.hunger, self.energy, self.social, self.fun))
        return _clamp(0.45 * vals[0] + 0.25 * vals[1] + 0.18 * vals[2] + 0.12 * vals[3] - 0.1 * (self.neuroticism - 0.5))

    def stage(self, t: int) -> str:
        a = self.age(t)
        if a < 3:
            return "baby"
        if a < 13:
            return "child"
        if a < 18:
            return "teen"
        if a < 65:
            return "adult"
        return "senior"


@dataclass(slots=True)
class Household:
    id: int
    home: int  # building id
    members: list[int]
    has_car: bool


def _clamp(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def urgency(v: float) -> float:
    """How pressing a need is: gentle when mostly satisfied, steep when low."""
    return (1.0 - v) ** 2 * 1.6 + (1.0 - v) * 0.4


def gompertz_annual(age: float, health: float = 1.0) -> float:
    """Yearly chance of dying: doubles about every 7.7 years of age (Gompertz law)."""
    return min(1.0, 0.00003 * math.exp(0.09 * age) * (1.0 + 1.5 * (1.0 - health)) + 0.0003)
