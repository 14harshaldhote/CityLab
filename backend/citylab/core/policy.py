"""The city's rules that a "what if?" can change.

Every lever is a plain number that the subsystems read each time they need it, so
changing one mid-run takes effect straight away and travels with the city in its
snapshots. ``LEVERS`` lists what the time machine offers, with a few sensible
settings for each.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


@dataclass
class Policy:
    bus_fare: float = 10.0  # rupees a ride (half for seniors, free under 12)
    income_tax: float = 0.15  # share of every pay packet
    benefit: float = 40.0  # rupees a day to someone looking for work
    patrols: float = 1.0  # police cars out, relative to normal

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    def changed(self) -> dict[str, float]:
        base = Policy()
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) != getattr(base, f.name)}


# key: (what it is called, how a value reads, the settings offered)
LEVERS: dict[str, dict[str, Any]] = {
    "bus_fare": {"name": "Bus fare", "unit": "a ride", "options": [0.0, 5.0, 10.0, 20.0, 40.0],
                 "story": "Cheaper buses pull people out of autos and off their feet; dearer ones push them back."},
    "income_tax": {"name": "Income tax", "unit": "of pay", "options": [0.0, 0.05, 0.15, 0.25, 0.4],
                   "story": "Tax fills the city's budget but leaves families with less to spend."},
    "benefit": {"name": "Help for people out of work", "unit": "a day", "options": [0.0, 20.0, 40.0, 80.0, 150.0],
                "story": "Hard times make theft tempting. Does a safety net change that?"},
    "patrols": {"name": "Police patrols", "unit": "the usual number", "options": [0.0, 0.5, 1.0, 2.0, 3.0],
                "story": "More police cars put more thieves off, and cost the city more fuel."},
    "base_rate": {"name": "Bank interest rate", "unit": "a year", "options": [0.02, 0.04, 0.06, 0.1, 0.15],
                  "story": "City Bank's rate sets what loans cost, and how much savers earn."},
}


def apply(world: Any, lever: str, value: float) -> None:
    """Change one lever in a running city."""
    if lever not in LEVERS:
        raise ValueError(f"unknown lever {lever!r}")
    if lever == "base_rate":
        world.economy.base_rate = float(value)
    else:
        setattr(world.policy, lever, float(value))


def describe(lever: str, v: float) -> str:
    """A lever's setting in words."""
    if lever in ("income_tax", "base_rate"):
        return f"{v * 100:.0f}%"
    if lever == "patrols":
        return "no patrols" if v == 0 else f"{v:g}× the usual patrols"
    return f"₹{v:,.0f}"


def current(world: Any) -> dict[str, float]:
    return {**world.policy.to_dict(), "base_rate": world.economy.base_rate}
