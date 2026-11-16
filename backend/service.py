"""Application services: queue state machine, table allocation and time-triggered events."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from . import storage
from .events import emit

DEMO_MODE = __import__("os").getenv("DEMO_MODE", "true").lower() == "true"
GRACE_MINUTES = int(__import__("os").getenv("GRACE_MINUTES", "30"))
PHONE_PROMISE_MINUTES = int(__import__("os").getenv("PHONE_PROMISE_MINUTES", "10"))
ACTIVE = ("WAITING", "DEFERRED", "CALLED")


def fail(status, message):
    raise HTTPException(status_code=status, detail=message)


def as_dict(row):
    return dict(row) if row else None


def load_ticket(con, ticket_id):
    row = con.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if not row:
        fail(404, "未找到此取号记录")
    return dict(row)


def name_prefix(n):
    return "A" if n <= 2 else "B" if n <= 4 else "C"


def new_ticket(name, party_size, arrival_at, phone="", request_id=None):
    if party_size < 1 or party_size > 6:
        fail(400, "演示版支持 1–6 人候位")
    arrival = storage.as_dt(arrival_at)
    with storage.transaction() as con:
        now = storage.clock(con)
        if arrival < now - timedelta(minutes=5) or arrival > now + timedelta(hours=8):
            fail(400, "预计到店时间需在当前附近至未来 8 小时内")
        req = request_id or str(uuid4())
        previous = con.execute("SELECT * FROM tickets WHERE request_id=?", (req,)).fetchone()
        if previous:
            return dict(previous)
        prefix = name_prefix(party_size)
        local_day = now.astimezone(ZoneInfo(storage.TIMEZONE)).strftime("%Y%m%d")
        con.execute("INSERT INTO counters(day,prefix,value) VALUES(?,?,1) ON CONFLICT(day,prefix) DO UPDATE SET value=value+1", (local_day,prefix))
        num = con.execute("SELECT value FROM counters WHERE day=? AND prefix=?",(local_day,prefix)).fetchone()[0]
        stamp = storage.iso(now)
        cur = con.execute("""INSERT INTO tickets(request_id,number,name,party_size,phone,arrival_at,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,'WAITING',?,?)""", (req, f"{prefix}{num:03d}", name.strip(), party_size, phone.strip(), storage.iso(arrival), stamp, stamp))
        emit(con,"TicketCreated",cur.lastrowid,f"{name} 取号 {prefix}{num:03d}",stamp)
        return load_ticket(con,cur.lastrowid)


def arrive(ticket_id):
    with storage.transaction() as con:
        ticket = load_ticket(con,ticket_id)
        now = storage.clock(con)
        if ticket["status"] not in ("WAITING", "DEFERRED"):
            fail(409,"当前状态无法登记到店")
        if ticket["checked_in_at"]:
            return ticket
        grace_end = storage.as_dt(ticket["arrival_at"]) + timedelta(minutes=GRACE_MINUTES)
        if now > grace_end:
            fail(409,"已超过候位宽限期，请重新取号")
        # Priority is only for a guest skipped when originally called early, and
        # who physically arrives within the promised arrival grace window.
        priority = int(ticket["status"]=="DEFERRED" and now <= grace_end and not ticket["promised_missed"])
        stamp = storage.iso(now)
        con.execute("UPDATE tickets SET status='WAITING',checked_in_at=?,priority=?,updated_at=? WHERE id=?", (stamp,priority,stamp,ticket_id))
        emit(con,"ArrivalConfirmed",ticket_id,f"{ticket['number']} 已到店"+(" · 优先候位" if priority else ""),stamp)
        return load_ticket(con,ticket_id)


def update_arrival(ticket_id, arrival_at):
    new = storage.as_dt(arrival_at)
    with storage.transaction() as con:
        item=load_ticket(con,ticket_id)
        now=storage.clock(con)
        if item["status"] not in ("WAITING","DEFERRED") or item["checked_in_at"]:
            fail(409,"当前不能修改预计到店时间")
        if not(now-timedelta(minutes=5) <= new <= now+timedelta(hours=8)):
            fail(400,"预计到店时间不在可调整范围")
        stamp=storage.iso(now)
        con.execute("UPDATE tickets SET arrival_at=?,phone_requested_at=NULL,phone_response=NULL,promise_deadline=NULL,promised_missed=0,updated_at=? WHERE id=?", (storage.iso(new),stamp,ticket_id))
        emit(con,"ArrivalUpdated",ticket_id,f"{item['number']} 修改预计到店时间",stamp)
        return load_ticket(con,ticket_id)


def cancel(ticket_id):
    with storage.transaction() as con:
        item=load_ticket(con,ticket_id)
        if item["status"] not in ("WAITING","DEFERRED"):
            fail(409,"当前无法取消候位")
        stamp=storage.iso(storage.clock(con))
        con.execute("UPDATE tickets SET status='CANCELLED',updated_at=? WHERE id=?", (stamp,ticket_id))
        emit(con,"TicketCancelled",ticket_id,f"{item['number']} 已取消",stamp)
        return load_ticket(con,ticket_id)


def phone_respond(ticket_id, response):
    if response not in ("on_way","cant"):
        fail(400,"未知回复")
    with storage.transaction() as con:
        item=load_ticket(con,ticket_id)
        now=storage.clock(con)
        if item["status"] not in ("WAITING","DEFERRED") or item["checked_in_at"]:
            fail(409,"当前状态无法回复电话确认")
        if not item["phone_requested_at"]:
            fail(409,"尚未收到电话确认请求")
        if item["phone_response"]:
            fail(409,"本次电话确认已处理")
        stamp=storage.iso(now)
        if response=="on_way":
            deadline=storage.iso(now+timedelta(minutes=PHONE_PROMISE_MINUTES))
            con.execute("UPDATE tickets SET phone_response='on_way',promise_deadline=?,updated_at=? WHERE id=?", (deadline,stamp,ticket_id))
            emit(con,"PhoneConfirmed",ticket_id,f"{item['number']} 承诺 {PHONE_PROMISE_MINUTES} 分钟内到店",stamp)
        else:
            con.execute("UPDATE tickets SET phone_response='cant',updated_at=? WHERE id=?", (stamp,ticket_id))
            emit(con,"PhoneDeclined",ticket_id,f"{item['number']} 回复暂时无法到店",stamp)
        return load_ticket(con,ticket_id)


def tick():
    """Run deterministic time-based state transitions; idempotent on repeat."""
    with storage.transaction() as con:
        now=storage.clock(con)
        stamp=storage.iso(now)
        changed=0
        rows=con.execute("SELECT * FROM tickets WHERE status IN ('WAITING','DEFERRED') AND checked_in_at IS NULL").fetchall()
        for row in rows:
            item=dict(row)
            arrival=storage.as_dt(item["arrival_at"])
            deadline=arrival+timedelta(minutes=GRACE_MINUTES)
            if now>deadline:
                con.execute("UPDATE tickets SET status='EXPIRED',updated_at=? WHERE id=?",(stamp,item["id"]))
                emit(con,"TicketExpired",item["id"],f"{item['number']} 超过到店宽限期",stamp)
                changed+=1
                continue
            if now>=arrival and not item["phone_requested_at"]:
                con.execute("UPDATE tickets SET phone_requested_at=?,updated_at=? WHERE id=?", (stamp,stamp,item["id"]))
                emit(con,"ArrivalReminder",item["id"],f"模拟电话：请确认 {PHONE_PROMISE_MINUTES} 分钟内能否到店",stamp)
                changed+=1
            if item["phone_response"]=="on_way" and not item["promised_missed"] and item["promise_deadline"] and now>storage.as_dt(item["promise_deadline"]):
                con.execute("UPDATE tickets SET promised_missed=1,priority=0,updated_at=? WHERE id=?", (stamp,item["id"]))
                emit(con,"PhoneMissed",item["id"],f"{item['number']} 未按承诺时间到店，取消特别优先权",stamp)
                changed+=1
        return changed


def call_next(table_id):
    """Atomic table selection and ticket claim. Non-arrived older tickets are deferred."""
    with storage.transaction() as con:
        tbl=con.execute("SELECT * FROM tables WHERE id=?",(table_id,)).fetchone()
        if not tbl: fail(404,"桌位不存在")
        if tbl["status"]!="FREE": fail(409,"此桌位尚未空闲")
        now=storage.clock(con)
        stamp=storage.iso(now)
        rows=con.execute("""SELECT * FROM tickets WHERE status IN ('WAITING','DEFERRED')
          AND party_size<=? ORDER BY priority DESC, created_at ASC, id ASC""", (tbl["capacity"],)).fetchall()
        candidate=None
        deferred=[]
        for row in rows:
            item=dict(row)
            if not item["checked_in_at"]:
                # The system does not reserve an empty table for an absent guest.
                if item["status"]=="WAITING":
                    con.execute("UPDATE tickets SET status='DEFERRED',updated_at=? WHERE id=?",(stamp,item["id"]))
                    emit(con,"TicketDeferred",item["id"],f"{item['number']} 未到店，暂缓叫号",stamp)
                    deferred.append(item["number"])
                continue
            candidate=item
            break
        if not candidate:
            return {"ticket": None, "deferred":deferred, "message":"暂无已到店且匹配的候位顾客"}
        con.execute("UPDATE tickets SET status='CALLED',called_at=?,table_id=?,priority=0,updated_at=? WHERE id=?", (stamp,table_id,stamp,candidate["id"]))
        con.execute("UPDATE tables SET status='HELD',ticket_id=? WHERE id=?",(candidate["id"],table_id))
        emit(con,"TicketCalled",candidate["id"],f"{candidate['number']} 请到 {tbl['name']} 就座",stamp)
        return {"ticket":load_ticket(con,candidate["id"]), "deferred":deferred,"message":"叫号成功"}


def seat(ticket_id):
    with storage.transaction() as con:
        item=load_ticket(con,ticket_id)
        if item["status"]!="CALLED": fail(409,"只有已叫号顾客可以确认入座")
        stamp=storage.iso(storage.clock(con))
        con.execute("UPDATE tickets SET status='SEATED',seated_at=?,updated_at=? WHERE id=?", (stamp,stamp,ticket_id))
        con.execute("UPDATE tables SET status='OCCUPIED' WHERE id=? AND ticket_id=?", (item["table_id"],ticket_id))
        emit(con,"TicketSeated",ticket_id,f"{item['number']} 已入座",stamp)
        return load_ticket(con,ticket_id)


def skip_called(ticket_id):
    with storage.transaction() as con:
        item=load_ticket(con,ticket_id)
        if item["status"]!="CALLED": fail(409,"只有已叫号顾客可以标记未到")
        stamp=storage.iso(storage.clock(con))
        con.execute("UPDATE tickets SET status='DEFERRED',checked_in_at=NULL,priority=0,table_id=NULL,updated_at=? WHERE id=?",(stamp,ticket_id))
        con.execute("UPDATE tables SET status='FREE',ticket_id=NULL WHERE id=? AND ticket_id=?",(item["table_id"],ticket_id))
        emit(con,"TicketDeferred",ticket_id,f"{item['number']} 叫号后未到，桌位已释放",stamp)
        return load_ticket(con,ticket_id)


def finish(table_id):
    with storage.transaction() as con:
        tbl=con.execute("SELECT * FROM tables WHERE id=?", (table_id,)).fetchone()
        if not tbl: fail(404,"桌位不存在")
        if tbl["status"]!="OCCUPIED": fail(409,"只有正在使用的桌位可以完成用餐")
        now=storage.iso(storage.clock(con))
        tid=tbl["ticket_id"]
        item=load_ticket(con,tid)
        con.execute("UPDATE tickets SET status='COMPLETED',finished_at=?,updated_at=? WHERE id=?",(now,now,tid))
        con.execute("UPDATE tables SET status='FREE',ticket_id=NULL WHERE id=?",(table_id,))
        emit(con,"TableReleased",tid,f"{tbl['name']} 空闲，可以叫下一桌",now)
        return {"table":dict(tbl),"ticket":load_ticket(con,tid)}


def advance(minutes):
    if not DEMO_MODE: fail(403,"非演示模式禁止修改时间")
    if minutes < -180 or minutes > 240: fail(400,"每次调整不得超过 -180 至 240 分钟")
    with storage.transaction() as con:
        value=int(con.execute("SELECT value FROM settings WHERE key='offset_minutes'").fetchone()[0])
        con.execute("UPDATE settings SET value=? WHERE key='offset_minutes'", (str(value+minutes),))
    tick()
    return {"offset_minutes":value+minutes}


def dashboard(include_details=True):
    """Use one committed snapshot for coherent dashboard reads."""
    with storage.connect() as con:
        ticket_rows=[dict(x) for x in con.execute("SELECT * FROM tickets ORDER BY created_at ASC,id ASC").fetchall()]
        table_rows=[dict(x) for x in con.execute("SELECT * FROM tables ORDER BY id").fetchall()]
        events=[dict(x) for x in con.execute("SELECT * FROM events ORDER BY id DESC LIMIT 14").fetchall()]
        now=storage.clock(con)
        valid=[x for x in ticket_rows if x["status"] in ("WAITING","DEFERRED","CALLED")]
        for x in ticket_rows:
            x["ahead"] = sum(1 for y in valid if y["id"] < x["id"] and y["status"] in ("WAITING","DEFERRED","CALLED") and y["party_size"]<=x["party_size"]+2) if x["status"] in ("WAITING","DEFERRED") else 0
        for t in table_rows:
            active=next((x for x in ticket_rows if x["id"]==t["ticket_id"]),None)
            t["ticket"]={"number":active["number"],"name":active["name"],"id":active["id"]} if active else None
        return {
            "now":storage.iso(now),
            "time_zone":storage.TIMEZONE,
            "demo_mode":DEMO_MODE,
            "grace_minutes":GRACE_MINUTES,
            "phone_minutes":PHONE_PROMISE_MINUTES,
            "tickets":ticket_rows if include_details else [],
            "tables":table_rows,
            "events":events,
            "stats":{
                "waiting":sum(1 for x in ticket_rows if x["status"] in ("WAITING","DEFERRED")),
                "arrived":sum(1 for x in ticket_rows if x["status"]=="WAITING" and x["checked_in_at"]),
                "seated":sum(1 for x in ticket_rows if x["status"]=="SEATED"),
                "free_tables":sum(1 for t in table_rows if t["status"]=="FREE"),
                "called":sum(1 for x in ticket_rows if x["status"]=="CALLED"),
            }
        }


def get_ticket(ticket_id):
    with storage.connect() as con:
        x=load_ticket(con,ticket_id)
        x["notifications"]=[dict(r) for r in con.execute("SELECT * FROM notifications WHERE ticket_id=? ORDER BY id DESC LIMIT 10",(ticket_id,))]
        if x["status"] in ("WAITING", "DEFERRED"):
            prefix=name_prefix(x["party_size"])
            x["ahead"]=con.execute("""SELECT COUNT(*) FROM tickets
                WHERE id<>? AND number LIKE ? AND status IN ('WAITING','DEFERRED','CALLED')
                AND (priority>? OR (priority=? AND (created_at<? OR (created_at=? AND id<?))))""",
                (ticket_id, prefix+'%', x["priority"], x["priority"], x["created_at"], x["created_at"], x["id"])).fetchone()[0]
        else:
            x["ahead"]=0
        return x


def reset_demo():
    if not DEMO_MODE: fail(403,"非演示模式禁止重置数据")
    with storage.transaction() as con:
        for table in ("notifications","events","tickets","tables","counters"):
            con.execute("DELETE FROM "+table)
        con.execute("UPDATE settings SET value='0' WHERE key='offset_minutes'")
        storage.seed(con)
    return {"ok":True}
