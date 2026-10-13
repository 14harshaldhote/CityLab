"""Simulation time.

The whole simulation counts in integer minutes since the city's founding moment
(``t = 0`` is midnight on ``EPOCH``). Integers keep every run exactly repeatable:
no floating-point drift, no wall-clock reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
DAYS_PER_YEAR = 365
MINUTES_PER_YEAR = DAYS_PER_YEAR * MINUTES_PER_DAY

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@dataclass(frozen=True, slots=True)
class SimTime:
    """A decoded simulation minute."""

    t: int

    @property
    def day(self) -> int:
        """Days since founding (day 0 is the first day)."""
        return self.t // MINUTES_PER_DAY

    @property
    def minute_of_day(self) -> int:
        return self.t % MINUTES_PER_DAY

    @property
    def hour(self) -> float:
        return self.minute_of_day / MINUTES_PER_HOUR

    @property
    def weekday(self) -> int:
        """0 = Monday. 2026-01-01 was a Thursday."""
        return (self.day + 3) % 7

    @property
    def is_weekend(self) -> bool:
        return self.weekday >= 5

    @property
    def datetime(self) -> datetime:
        return EPOCH + timedelta(minutes=self.t)

    @property
    def unix(self) -> float:
        return self.datetime.timestamp()

    def label(self) -> str:
        d = self.datetime
        return f"{WEEKDAYS[self.weekday]} {d:%d %b %Y %H:%M}"


def minutes(days: float = 0, hours: float = 0, mins: float = 0) -> int:
    return int(round(days * MINUTES_PER_DAY + hours * MINUTES_PER_HOUR + mins))


def years_between(t_birth: int, t_now: int) -> float:
    return (t_now - t_birth) / MINUTES_PER_YEAR
