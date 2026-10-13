"""HTTP and WebSocket API."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ..core.clock import SimTime
from ..core.people import ACTIVITY_NAMES
from ..services.runner import MAX_SPEED, Runner

router = APIRouter(prefix="/api")


def runner(request: Request) -> Runner:
    return request.app.state.runner


class Control(BaseModel):
    playing: bool | None = None
    speed: float | None = Field(default=None, ge=0, le=MAX_SPEED)
    advance_minutes: int | None = Field(default=None, ge=1, le=7 * 24 * 60)


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
    out["activities"] = list(ACTIVITY_NAMES)
    return out


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
        card["life"] = [_event(e) for e in r.store.query(person=pid, limit=100)]
    return card


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
        )
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
        return [_event(e) for e in r.store.query(kind=kind, person=person, before=before, limit=limit)]


@router.get("/stats/daily")
def daily(request: Request, last: int = Query(3650, ge=1)) -> list[dict[str, Any]]:
    r = runner(request)
    with r.lock:
        return [{k: v for k, v in row.items() if k != "social"} | {"ties": row["social"]["ties"]} for row in r.world.daily[-last:]]


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
