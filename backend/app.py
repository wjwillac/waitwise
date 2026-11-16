"""HTTP API and static frontend for the WaitWise Codespaces project."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import service, storage

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
ADMIN_PIN = os.getenv("ADMIN_PIN", "123456")


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    async def clock_worker():
        while True:
            try:
                await asyncio.to_thread(service.tick)
            except Exception as exc:
                print(f"clock worker error: {exc}")
            await asyncio.sleep(8)
    task = asyncio.create_task(clock_worker())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="WaitWise · 智能候位系统", version="0.1.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND), name="assets")


def require_admin(x_admin_pin: str | None = Header(default=None)):
    if x_admin_pin != ADMIN_PIN:
        raise HTTPException(status_code=401, detail="商家演示 PIN 不正确")


class TicketIn(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    party_size: int = Field(ge=1, le=6)
    arrival_at: str
    phone: str = Field(default="", max_length=30)
    request_id: str = Field(default_factory=lambda: str(uuid4()), max_length=100)


class ArrivalIn(BaseModel):
    arrival_at: str


class PhoneReply(BaseModel):
    response: str


class TableAction(BaseModel):
    table_id: int


class ClockAction(BaseModel):
    minutes: int = Field(ge=-180, le=240)


@app.get("/")
def customer():
    return FileResponse(FRONTEND / "index.html")


@app.get("/staff")
def staff():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version}


@app.get("/api/dashboard")
def dashboard(x_admin_pin: str | None = Header(default=None)):
    result = service.dashboard(include_details=x_admin_pin == ADMIN_PIN)
    if x_admin_pin != ADMIN_PIN:
        # Public page needs only aggregate counts and available table information.
        result["tables"]=[{"id":x["id"],"capacity":x["capacity"],"status":x["status"]} for x in result["tables"]]
        result["events"]=[]
    return result


@app.post("/api/tickets", status_code=201)
def create_ticket(req: TicketIn):
    return service.new_ticket(req.name,req.party_size,req.arrival_at,req.phone,req.request_id)


@app.get("/api/tickets/{ticket_id}")
def ticket(ticket_id: int):
    # Demo-only access model. Production must use authenticated owner sessions.
    return service.get_ticket(ticket_id)


@app.post("/api/tickets/{ticket_id}/arrive")
def arrive(ticket_id: int):
    return service.arrive(ticket_id)


@app.post("/api/tickets/{ticket_id}/arrival")
def arrival(ticket_id: int, req: ArrivalIn):
    return service.update_arrival(ticket_id, req.arrival_at)


@app.post("/api/tickets/{ticket_id}/phone-reply")
def phone_reply(ticket_id: int, req: PhoneReply):
    return service.phone_respond(ticket_id, req.response)


@app.post("/api/tickets/{ticket_id}/cancel")
def cancel(ticket_id: int):
    return service.cancel(ticket_id)


@app.post("/api/admin/verify")
def verify_admin(x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    return {"ok":True}


@app.post("/api/admin/tick")
def tick(x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    return {"changed":service.tick()}


@app.post("/api/admin/call-next")
def call_next(req:TableAction,x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    return service.call_next(req.table_id)


@app.post("/api/admin/seat/{ticket_id}")
def seat(ticket_id:int,x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    return service.seat(ticket_id)


@app.post("/api/admin/skip/{ticket_id}")
def skip(ticket_id:int,x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    return service.skip_called(ticket_id)


@app.post("/api/admin/finish")
def finish(req:TableAction,x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    return service.finish(req.table_id)


@app.post("/api/admin/time-travel")
def time_travel(req:ClockAction,x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    return service.advance(req.minutes)


@app.post("/api/admin/reset-demo")
def reset(x_admin_pin: str | None = Header(default=None)):
    require_admin(x_admin_pin)
    return service.reset_demo()
