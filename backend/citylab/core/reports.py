"""Monthly and yearly reports, written from the city's daily statistics.

Each night the city adds one row of numbers to ``world.daily``. A report folds a
month's (or a year's) rows into totals, end-of-period figures and a few plain
sentences, the way a municipal annual report would.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from .clock import MINUTES_PER_DAY, SimTime

SUMS = ("births", "deaths", "arrived", "left", "couples", "hired", "crimes", "arrests", "convicted", "stolen", "trips_bus", "trips_auto",
        "trips_car", "trips_walk", "late", "gdp", "tax")
ENDS = ("population", "households", "employed", "unemployed", "median_balance", "city", "loans_outstanding", "in_debt", "in_jail", "cameras")


def covered_day(row: dict[str, Any]) -> int:
    """A row is written at midnight, so it describes the day before."""
    return max(0, int(row["day"]) - 1)


def month_key(day: int) -> str:
    return f"{SimTime(day * MINUTES_PER_DAY).datetime:%Y-%m}"


def year_key(day: int) -> str:
    return f"{SimTime(day * MINUTES_PER_DAY).datetime:%Y}"


def group(rows: list[dict[str, Any]], by: str = "month") -> OrderedDict[str, list[dict[str, Any]]]:
    key = month_key if by == "month" else year_key
    out: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in rows:
        out.setdefault(key(covered_day(row)), []).append(row)
    return out


def summarise(rows: list[dict[str, Any]], before: dict[str, Any] | None, opened: int = 0) -> dict[str, Any]:
    first, last = covered_day(rows[0]), covered_day(rows[-1])
    out: dict[str, Any] = {
        "first_day": first,
        "last_day": last,
        "days": len(rows),
        "opened": opened,
        "population_start": before["population"] if before else rows[0]["population"] - _net(rows[0]),
    }
    for k in SUMS:
        out[k] = round(sum(float(r.get(k) or 0) for r in rows), 2)
    for k in ENDS:
        out[k] = rows[-1].get(k)
    commutes = [r["commute_min"] for r in rows if r.get("commute_min")]
    out["commute_min"] = round(sum(commutes) / len(commutes), 1) if commutes else None
    return out


def _net(row: dict[str, Any]) -> int:
    return int(row.get("births", 0)) - int(row.get("deaths", 0)) + int(row.get("arrived", 0)) - int(row.get("left", 0))


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _people(n: float, one: str, many: str) -> str:
    if round(n) == 0:
        return f"no {many.split()[0]}" + (f" {' '.join(many.split()[1:])}" if len(many.split()) > 1 else "")
    return f"{_n(n)} {one if round(n) == 1 else many}"


def story(rep: dict[str, Any], name: str, period: str) -> str:
    """A short paragraph in plain words."""
    start, end = rep["population_start"], rep["population"]
    change = "grew" if end > start else "shrank" if end < start else "held steady"
    s = [
        f"In {period} {name} {change} from {_n(start)} to {_n(end)} people: "
        f"{_people(rep['births'], 'baby was', 'babies were')} born, {_people(rep['deaths'], 'person', 'people')} died, "
        f"{_n(rep['arrived'])} moved in and {_n(rep['left'])} moved away.",
        f"{_people(rep['couples'], 'couple', 'couples')} got together and {_people(rep['hired'], 'person', 'people')} found a job; "
        f"{_n(rep['unemployed'] or 0)} {'was' if rep['unemployed'] == 1 else 'were'} still looking at the end.",
    ]
    if rep["opened"]:
        s.append(f"{_people(rep['opened'], 'new building', 'new buildings')} opened.")
    s.append(f"The city collected ₹{_n(rep['tax'])} in tax and ended with ₹{_n(rep['city'] or 0)} in its budget.")
    if rep["crimes"]:
        s.append(f"Police recorded {_people(rep['crimes'], 'theft', 'thefts')} worth ₹{_n(rep['stolen'])}, made "
                 f"{_people(rep['arrests'], 'arrest', 'arrests')}, and the court found {_people(rep['convicted'], 'person', 'people')} guilty.")
    else:
        s.append("Not a single theft was recorded.")
    if rep["trips_bus"]:
        s.append(f"City buses carried {_n(rep['trips_bus'])} riders" + (f", and the trip to work took {rep['commute_min']} minutes on average." if rep["commute_min"] else "."))
    return " ".join(s)


def reports(rows: list[dict[str, Any]], finished: list[dict[str, Any]], name: str, by: str = "month") -> list[dict[str, Any]]:
    """Every month (or year) so far, newest first. The current, unfinished one is marked."""
    groups = group(rows, by)
    out = []
    before = None
    key = month_key if by == "month" else year_key
    opened: dict[str, int] = {}
    for f in finished:
        if f.get("day") is not None:
            opened[key(int(f["day"]))] = opened.get(key(int(f["day"])), 0) + 1
    for k, grp in groups.items():
        rep = summarise(grp, before, opened.get(k, 0))
        d = SimTime(rep["first_day"] * MINUTES_PER_DAY).datetime
        period = f"{d:%B %Y}" if by == "month" else f"{d:%Y}"
        rep.update({"key": k, "period": period, "text": story(rep, name, period)})
        out.append(rep)
        before = grp[-1]
    if out:
        last_day = covered_day(rows[-1])
        nxt = SimTime((last_day + 1) * MINUTES_PER_DAY).datetime
        out[-1]["complete"] = (nxt.day == 1) if by == "month" else (nxt.month == 1 and nxt.day == 1)
        for rep in out[:-1]:
            rep["complete"] = True
    return out[::-1]
