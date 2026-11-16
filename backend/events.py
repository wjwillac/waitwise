"""Persistent domain events and in-process notification subscriber.

For this teaching MVP, event + projection are stored in the same SQLite
transaction. A production distributed design could replace the subscriber with
an outbox/worker without changing service methods.
"""
from __future__ import annotations

import json

NOTIFICATION_TEMPLATES = {
    "TicketCreated": ("取号成功", "已收到你的候位申请，请留意排队进度。"),
    "TicketDeferred": ("已暂缓叫号", "轮到你时尚未到店，餐厅将先安排已到店顾客。"),
    "ArrivalReminder": ("到店确认", "已到预计到店时间。请确认能否在 10 分钟内到达。"),
    "ArrivalConfirmed": ("到店登记成功", "已登记到店，系统将按候位规则安排。"),
    "TicketCalled": ("轮到你啦", "请根据服务员提示前往对应桌位。"),
    "TicketSeated": ("入座成功", "祝你用餐愉快！"),
    "TicketExpired": ("候位已过期", "超过预计到店时间后的宽限期，请重新取号。"),
    "TicketCancelled": ("已取消候位", "本次候位已取消。"),
    "PhoneConfirmed": ("已确认到店时间", "已记录你将于 10 分钟内到店的回复。"),
    "PhoneMissed": ("承诺到店时间已过", "你的优先候位资格已调整，请尽快联系餐厅。"),
}


def emit(con, event_type, ticket_id, message, created_at, data=None):
    payload = {"message": message, **(data or {})}
    con.execute("INSERT INTO events(type,ticket_id,payload,created_at) VALUES(?,?,?,?)", (event_type, ticket_id, json.dumps(payload, ensure_ascii=False), created_at))
    if ticket_id is not None and event_type in NOTIFICATION_TEMPLATES:
        title, body = NOTIFICATION_TEMPLATES[event_type]
        con.execute("INSERT INTO notifications(ticket_id,title,body,created_at) VALUES(?,?,?,?)", (ticket_id, title, body, created_at))
