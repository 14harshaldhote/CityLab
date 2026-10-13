"""What if? Two copies of the city, played forward side by side.

Both copies start from the very same moment. One keeps the city's rules as they
are, the other has one rule changed. Each runs in its own process (so the live
city keeps running), and at the end the two are compared: totals, end figures,
and how many people ended up somewhere different, which shows how a small change
ripples through a whole city.
"""

from __future__ import annotations

import itertools
import logging
import multiprocessing as mp
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from ..core import policy
from ..core.clock import MINUTES_PER_DAY, SimTime
from ..core.people import ACTIVITY_NAMES
from ..core.world import World
from .history import freeze, thaw

log = logging.getLogger("citylab.whatif")

# (key, label, how it is measured, True if more is better for the people of the city)
MEASURES: tuple[tuple[str, str, str, bool | None], ...] = (
    ("population", "People", "end", None),
    ("unemployed", "Looking for work", "end", False),
    ("median_balance", "Typical bank balance (₹)", "end", True),
    ("in_debt", "People in debt", "end", False),
    ("city", "City budget (₹)", "end", True),
    ("tax", "Tax collected (₹)", "sum", None),
    ("crimes", "Thefts", "sum", False),
    ("arrests", "Arrests", "sum", None),
    ("trips_bus", "Bus rides", "sum", None),
    ("trips_auto", "Auto rides", "sum", None),
    ("trips_walk", "Walks", "sum", None),
    ("late", "People late for work", "sum", False),
    ("births", "Babies born", "sum", None),
)
DAYS = (3, 7, 14, 30)


def _play(blob: bytes, events: int, changes: dict[str, float], days: int, out: Any, tag: str) -> None:
    """Runs in a child process: thaw the city, change its rules, play it forward a day at a time."""
    try:
        w = thaw(blob, events)
        for lever, value in changes.items():
            policy.apply(w, lever, value)
        start_rows = len(w.daily)
        kinds: dict[str, int] = {}
        stories: list[str] = []

        def note(e: Any) -> None:
            kinds[e.kind] = kinds.get(e.kind, 0) + 1
            if e.kind in ("crime", "arrest", "court", "laid_off", "default", "loan", "left", "birth", "couple", "opened", "cctv"):
                stories.append(f"{SimTime(e.t).label()} · {e.text}")

        w.bus.subscribe("*", note)
        end = (w.t // MINUTES_PER_DAY + days) * MINUTES_PER_DAY
        day = 0
        while w.t < end:
            w.advance(min(MINUTES_PER_DAY - w.t % MINUTES_PER_DAY, end - w.t))
            day += 1
            out.put((tag, "progress", day))
        rows = [{k: v for k, v in r.items() if k not in ("social", "religions", "festival")} for r in w.daily[start_rows:]]
        bal = w.economy.balance
        where = {p.id: (p.place, p.activity, round(bal.get(w.economy.person(p.id), 0.0))) for p in w.people.values() if p.alive}
        out.put((tag, "done", {"rows": rows, "kinds": kinds, "stories": stories[-40:], "where": where, "t": w.t}))
    except Exception as exc:  # report, don't hang the parent
        out.put((tag, "error", repr(exc)))


@dataclass
class Job:
    id: int
    lever: str
    value: float
    was: float
    days: int
    start_t: int
    status: str = "running"  # running | done | failed | cancelled
    progress: dict[str, int] = field(default_factory=lambda: {"same": 0, "changed": 0})
    result: dict[str, Any] | None = None
    error: str | None = None
    started: float = field(default_factory=time.time)
    procs: list[Any] = field(default_factory=list)

    def view(self) -> dict[str, Any]:
        info = policy.LEVERS[self.lever]
        return {
            "id": self.id, "lever": self.lever, "lever_name": info["name"], "unit": info["unit"], "value": self.value, "was": self.was,
            "days": self.days, "from": SimTime(self.start_t).label(), "status": self.status,
            "progress": round(min(self.progress.values()) / self.days, 3), "error": self.error, "result": self.result,
        }


class WhatIfs:
    def __init__(self) -> None:
        self.jobs: dict[int, Job] = {}
        self._ids = itertools.count(1)
        self.lock = threading.Lock()
        self.ctx = mp.get_context("spawn")

    def start(self, world: World, lever: str, value: float, days: int) -> Job:
        if lever not in policy.LEVERS:
            raise ValueError(f"unknown lever {lever!r}")
        was = policy.current(world)[lever]
        blob, events = freeze(world), world.bus.count
        job = Job(next(self._ids), lever, float(value), was, int(days), world.t)
        self.cancel_running()
        q = self.ctx.Queue()
        for tag, changes in (("same", {}), ("changed", {lever: float(value)})):
            proc = self.ctx.Process(target=_play, args=(blob, events, changes, job.days, q, tag), daemon=True)
            proc.start()
            job.procs.append(proc)
        with self.lock:
            self.jobs[job.id] = job
            for old in sorted(self.jobs)[:-5]:  # remember the last five
                del self.jobs[old]
        threading.Thread(target=self._collect, args=(job, q), daemon=True).start()
        return job

    def _collect(self, job: Job, q: Any) -> None:
        results: dict[str, dict[str, Any]] = {}
        while len(results) < 2 and job.status == "running":
            try:
                tag, what, payload = q.get(timeout=1.0)
            except Exception:
                if not any(p.is_alive() for p in job.procs):
                    job.status, job.error = "failed", "the simulation stopped unexpectedly"
                continue
            if what == "progress":
                job.progress[tag] = payload
            elif what == "done":
                results[tag] = payload
            else:
                job.status, job.error = "failed", payload
        for p in job.procs:
            p.join(timeout=2)
        job.procs = []
        if job.status == "running":
            job.result = compare(results["same"], results["changed"], job)
            job.status = "done"

    def cancel_running(self) -> None:
        with self.lock:
            running = [j for j in self.jobs.values() if j.status == "running"]
        for j in running:
            j.status = "cancelled"
            for p in j.procs:
                p.terminate()

    def get(self, jid: int) -> Job | None:
        return self.jobs.get(jid)

    def latest(self) -> Job | None:
        return self.jobs[max(self.jobs)] if self.jobs else None


def _measure(rows: list[dict[str, Any]], key: str, how: str) -> float:
    if not rows:
        return 0.0
    if how == "end":
        return float(rows[-1].get(key) or 0)
    return float(sum(r.get(key) or 0 for r in rows))


def compare(same: dict[str, Any], changed: dict[str, Any], job: Job) -> dict[str, Any]:
    """Line the two cities up: what changed, by how much, and how far the ripples spread."""
    measures = []
    for key, label, how, good in MEASURES:
        a, b = _measure(same["rows"], key, how), _measure(changed["rows"], key, how)
        measures.append({"key": key, "label": label, "how": how, "same": round(a, 1), "changed": round(b, 1), "diff": round(b - a, 1),
                         "better": None if good is None or a == b else (b > a) == good})
    common = set(same["where"]) & set(changed["where"])
    moved = sum(1 for pid in common if same["where"][pid][0] != changed["where"][pid][0])
    doing = sum(1 for pid in common if same["where"][pid][1] != changed["where"][pid][1])
    touched = sum(1 for pid in common if same["where"][pid] != changed["where"][pid])
    ripple = round(touched / max(1, len(common)), 3)
    return {
        "measures": measures,
        "ripple": ripple,
        "touched": touched,
        "elsewhere": moved,
        "doing_else": doing,
        "people": len(common),
        "same_rows": same["rows"],
        "changed_rows": changed["rows"],
        "stories": changed["stories"][-12:][::-1],
        "story": _story(job, measures, ripple),
        "activities": list(ACTIVITY_NAMES),
    }


def _amount(label: str, v: float) -> str:
    return f"₹{v:,.0f}" if "(₹)" in label else f"{v:,.0f}"


def _story(job: Job, measures: list[dict[str, Any]], ripple: float) -> str:
    name = policy.LEVERS[job.lever]["name"].lower()
    s = [f"Changing the {name} from {policy.describe(job.lever, job.was)} to {policy.describe(job.lever, job.value)} for {job.days} days:"]
    moved = []
    for m in measures:
        a, b = m["same"], m["changed"]
        rel = (b - a) / abs(a) if a else (1.0 if b else 0.0)
        if abs(rel) >= 0.05 and abs(b - a) >= 2:
            moved.append((abs(rel), m))
    moved.sort(key=lambda x: -x[0])
    lines = []
    for _, m in moved[:4]:
        label = m["label"].replace(" (₹)", "")
        a, b = _amount(m["label"], m["same"]), _amount(m["label"], m["changed"])
        if m["how"] == "sum":
            lines.append(f"{b} {label.lower()} instead of {a}")
        else:
            lines.append(f"{label.lower()} {'up' if m['changed'] > m['same'] else 'down'} to {b} from {a}")
    if lines:
        s.append("; ".join(lines) + ".")
    else:
        s.append("the big numbers hardly moved.")
    return " ".join(s)
