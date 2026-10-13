"""HTTP and WebSocket API."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..core import policy, reports
from ..core.clock import SimTime
from ..core.people import ACTIVITY_NAMES
from ..services.whatif import DAYS
from ..services.runner import MAX_SPEED, Runner

router = APIRouter(prefix="/api")


def runner(request: Request) -> Runner:
    return request.app.state.runner


class Control(BaseModel):
    playing: bool | None = None
    speed: float | None = Field(default=None, ge=0, le=MAX_SPEED)
    advance_minutes: int | None = Field(default=None, ge=1, le=7 * 24 * 60)


class Travel(BaseModel):
    t: int = Field(ge=0)


class Lever(BaseModel):
    lever: str
    value: float


class WhatIf(Lever):
    days: int = Field(default=7)


class Reset(BaseModel):
    seed: int = Field(default=1, ge=0)
    population: int = Field(default=2000, ge=10, le=20000)


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    r = runner(request)
    return {"ok": True, "t": r.world.t, "database": r.pg is not None}


@router.get("/city")
def city(request: Request) -> dict[str, Any]:
    r = runner(request)
    with r.lock:
        out = r.world.city.to_dict()
        out["transit"] = r.world.transport.network()
        out["cameras"] = r.world.crime.cameras_view()
    out["activities"] = list(ACTIVITY_NAMES)
    return out


@router.get("/agencies")
def agencies(request: Request) -> dict[str, Any]:
    r = runner(request)
    with r.lock:
        return r.world.government.view()


@router.get("/transport")
def transport(request: Request) -> dict[str, Any]:
    r = runner(request)
    with r.lock:
        return r.world.transport.view()


@router.get("/safety")
def safety(request: Request) -> dict[str, Any]:
    r = runner(request)
    with r.lock:
        return r.world.crime.view()


@router.get("/frame")
def frame(request: Request) -> dict[str, Any]:
    return runner(request).frame()


@router.get("/summary")
def summary(request: Request) -> dict[str, Any]:
    r = runner(request)
    with r.lock:
        out = r.world.summary()
    out.update(playing=r.playing, speed=r.speed, step_ms=round(r.last_step_s * 1000, 1), seed=r.world.seed)
    return out


@router.post("/control")
def control(body: Control, request: Request) -> dict[str, Any]:
    r = runner(request)
    r.set(playing=body.playing, speed=body.speed)
    if body.advance_minutes:
        r.step(body.advance_minutes)
    return {"playing": r.playing, "speed": r.speed, "t": r.world.t}


@router.post("/reset")
def reset(body: Reset, request: Request) -> dict[str, Any]:
    r = runner(request)
    r.reset(body.seed, body.population)
    return {"seed": body.seed, "population": len(r.world.alive())}


@router.get("/people")
def people(request: Request, q: str = "", limit: int = Query(20, ge=1, le=200)) -> list[dict[str, Any]]:
    r = runner(request)
    needle = q.lower().strip()
    out = []
    with r.lock:
        t = r.world.t
        for p in r.world.people.values():
            if needle and needle not in p.name.lower():
                continue
            out.append({"id": p.id, "name": p.name, "age": int(p.age(t if p.alive else p.died or t)), "alive": p.alive,
                        "activity": ACTIVITY_NAMES[p.activity] if p.alive else None})
            if len(out) >= limit:
                break
    return out


@router.get("/people/{pid}")
def person(pid: int, request: Request) -> dict[str, Any]:
    r = runner(request)
    with r.lock:
        if pid not in r.world.people:
            raise HTTPException(404, "no such person")
        card = r.world.person_card(pid)
        card["life"] = [_event(e) for e in r.store.query(person=pid, limit=100, upto=r.world.bus.count)]
    return card


@router.get("/people/{pid}/network")
def network(pid: int, request: Request, limit: int = Query(25, ge=1, le=100)) -> dict[str, Any]:
    """The person's corner of the social graph: their strongest ties and the ties among those people."""
    r = runner(request)
    with r.lock:
        g = r.world.social.g
        if pid not in g:
            raise HTTPException(404, "no such living person")
        nbrs = sorted(g[pid].items(), key=lambda kv: (-kv[1]["w"], kv[0]))[:limit]
        keep = [pid] + [int(v) for v, _ in nbrs]
        sub = g.subgraph(keep)
        people = r.world.people
        return {
            "center": pid,
            "nodes": [{"id": v, "name": people[v].name, "age": int(people[v].age(r.world.t))} for v in keep],
            "links": [{"source": int(a), "target": int(b), "strength": round(d["w"], 2), "kind": d["kind"]} for a, b, d in sub.edges(data=True)],
        }


@router.get("/buildings/{bid}")
def building(bid: int, request: Request) -> dict[str, Any]:
    r = runner(request)
    w = r.world
    with r.lock:
        if not 0 <= bid < len(w.city.buildings):
            raise HTTPException(404, "no such building")
        b = w.city.buildings[bid]
        st = w.now
        inside = [p for p in w.alive() if p.place == bid]
        residents = [q for hh in w.occupancy.get(bid, []) for q in w.households[hh].members]
        out = b.to_dict()
        out.update(
            open=b.is_open(st.minute_of_day, st.is_weekend),
            inside=[{"id": p.id, "name": p.name, "activity": ACTIVITY_NAMES[p.activity]} for p in inside[:50]],
            inside_count=len(inside),
            residents=len(residents),
            workers=len(w.job_holders.get(bid, [])),
            pupils=len(w.pupils.get(bid, [])),
            company=w.economy.company_view(bid),
        )
    return out


@router.get("/economy")
def economy(request: Request) -> dict[str, Any]:
    r = runner(request)
    with r.lock:
        econ = r.world.economy
        out = econ.summary()
        companies = econ.companies()
        out["richest_companies"] = companies[:8]
        out["struggling_companies"] = [c for c in reversed(companies) if c["balance"] < 0][:8]
        out["loan_rate_typical"] = econ.loan_rate("p:-1")
    return out


@router.get("/events")
def events(
    request: Request,
    kind: str | None = None,
    person: int | None = None,
    before: int | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict[str, Any]]:
    r = runner(request)
    with r.lock:
        return [_event(e) for e in r.store.query(kind=kind, person=person, before=before, limit=limit, upto=r.world.bus.count)]


@router.get("/stats/daily")
def daily(request: Request, last: int = Query(3650, ge=1)) -> list[dict[str, Any]]:
    r = runner(request)
    with r.lock:
        return [{k: v for k, v in row.items() if k != "social"} | {"ties": row["social"]["ties"]} for row in r.world.daily[-last:]]


@router.get("/history")
def history(request: Request) -> dict[str, Any]:
    """The time machine: how far back the city can go, its rules, and the latest what-if."""
    r = runner(request)
    with r.lock:
        out = r.history.view()
        out.update(t=r.world.t, label=r.world.now.label(), rules=policy.current(r.world))
    out["levers"] = policy.LEVERS
    out["whatif_days"] = list(DAYS)
    job = r.whatifs.latest()
    out["whatif"] = job.view() if job else None
    return out


@router.post("/travel")
def travel(body: Travel, request: Request) -> dict[str, Any]:
    return runner(request).travel(body.t)


@router.post("/rules")
def rules(body: Lever, request: Request) -> dict[str, Any]:
    if body.lever not in policy.LEVERS:
        raise HTTPException(422, "no such rule")
    return runner(request).change(body.lever, body.value)


@router.post("/whatif")
def whatif(body: WhatIf, request: Request) -> dict[str, Any]:
    r = runner(request)
    if body.lever not in policy.LEVERS:
        raise HTTPException(422, "no such rule")
    if body.days not in DAYS:
        raise HTTPException(422, f"days must be one of {DAYS}")
    with r.lock:
        job = r.whatifs.start(r.world, body.lever, body.value, body.days)
    return job.view()


@router.get("/whatif/{jid}")
def whatif_job(jid: int, request: Request) -> dict[str, Any]:
    job = runner(request).whatifs.get(jid)
    if job is None:
        raise HTTPException(404, "no such what-if")
    return job.view()


@router.delete("/whatif")
def whatif_cancel(request: Request) -> dict[str, Any]:
    runner(request).whatifs.cancel_running()
    return {"ok": True}


@router.get("/reports")
def city_reports(request: Request, by: str = Query("month", pattern="^(month|year)$")) -> list[dict[str, Any]]:
    r = runner(request)
    with r.lock:
        w = r.world
        return reports.reports(w.daily, w.government.finished, w.city.name, by)


@router.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    r: Runner = socket.app.state.runner
    await socket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=2)
    r.viewers.add(queue)
    try:
        await socket.send_json(r.frame())
        while True:
            frame = await queue.get()
            await socket.send_json(frame)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        r.viewers.discard(queue)


def _event(e) -> dict[str, Any]:
    d = e.to_dict()
    d["when"] = SimTime(e.t).label()
    if e.kind == "day_summary":
        d["data"] = {k: v for k, v in e.data.items() if k != "social"}
    return d
