"""Reproducible end-to-end API checks. All tests use disposable SQLite databases."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from backend import service, storage
from backend.app import app

PIN = {"X-Admin-Pin":"123456"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("WAITWISE_DB", str(tmp_path/"run.sqlite3"))
    with TestClient(app) as c:
        yield c


def new(client, name="测试顾客", party=2, delta=60, request_id=None):
    now=storage.clock()
    return client.post("/api/tickets",json={
        "name":name,"party_size":party,"arrival_at":storage.iso(now+timedelta(minutes=delta)),
        "request_id":request_id or str(uuid.uuid4())
    })


def test_page_and_health(client):
    assert client.get('/').status_code==200
    assert '候一会' in client.get('/').text
    assert client.get('/staff').status_code==200
    assert client.get('/api/health').json()['ok']


def test_create_and_idempotency(client):
    key=str(uuid.uuid4())
    a=new(client,request_id=key)
    b=new(client,request_id=key)
    assert a.status_code==201 and a.json()['id']==b.json()['id']
    assert a.json()['number'].startswith('A')


def test_concurrent_number_uniqueness(client):
    when=storage.iso(storage.clock()+timedelta(minutes=70))
    def create(i):
        return service.new_ticket(f"顾客{i}",2,when,request_id=str(uuid.uuid4()))
    with ThreadPoolExecutor(max_workers=10) as pool:
        numbers=[x['number'] for x in pool.map(create,range(20))]
    assert len(set(numbers))==20


def test_admin_requires_pin(client):
    assert client.post('/api/admin/call-next',json={'table_id':1}).status_code==401
    assert client.post('/api/admin/verify',headers=PIN).status_code==200


def test_call_skips_absent_then_seat_and_finish(client):
    r=client.post('/api/admin/call-next',json={'table_id':1},headers=PIN)
    assert r.status_code==200
    chosen=r.json()['ticket']
    assert chosen is not None and chosen['checked_in_at']
    seat=client.post(f"/api/admin/seat/{chosen['id']}",headers=PIN)
    assert seat.json()['status']=='SEATED'
    finished=client.post('/api/admin/finish',json={'table_id':1},headers=PIN)
    assert finished.json()['ticket']['status']=='COMPLETED'
    assert client.get('/api/dashboard',headers=PIN).json()['tables'][0]['status']=='FREE'


def test_early_skip_arrival_priority(client):
    # first absent guest joins after already checked-in demo guests; get them out of queue
    for table_id in (1,3):
        result=client.post('/api/admin/call-next',json={'table_id':table_id},headers=PIN).json()
        if result['ticket']:
            client.post(f"/api/admin/seat/{result['ticket']['id']}",headers=PIN)
    # now newly created absent guest is deferred when a table opens
    a=new(client,name='优先候位',delta=15).json()
    response=client.post('/api/admin/call-next',json={'table_id':2},headers=PIN)
    assert response.status_code==200
    row=client.get(f"/api/tickets/{a['id']}").json()
    assert row['status']=='DEFERRED'
    arrived=client.post(f"/api/tickets/{a['id']}/arrive")
    assert arrived.status_code==200
    assert arrived.json()['priority']==1


def test_time_reminder_and_reply(client):
    a=new(client,name='电话确认',delta=5).json()
    assert client.post('/api/admin/time-travel',json={'minutes':6},headers=PIN).status_code==200
    current=client.get(f"/api/tickets/{a['id']}").json()
    assert current['phone_requested_at'] is not None
    assert client.post(f"/api/tickets/{a['id']}/phone-reply",json={'response':'on_way'}).json()['phone_response']=='on_way'
    notices=client.get(f"/api/tickets/{a['id']}").json()['notifications']
    assert any(x['title']=='到店确认' for x in notices)


def test_grace_expiry(client):
    a=new(client,name='超时顾客',delta=5).json()
    client.post('/api/admin/time-travel',json={'minutes':36},headers=PIN)
    result=client.get(f"/api/tickets/{a['id']}").json()
    assert result['status']=='EXPIRED'
    assert client.post(f"/api/tickets/{a['id']}/arrive").status_code==409


def test_cancel_and_no_double_cancel(client):
    item=new(client,name='主动取消').json()
    assert client.post(f"/api/tickets/{item['id']}/cancel").json()['status']=='CANCELLED'
    assert client.post(f"/api/tickets/{item['id']}/cancel").status_code==409


def test_demo_reset(client):
    new(client)
    n=client.get('/api/dashboard',headers=PIN).json()['stats']['waiting']
    assert n>=7
    assert client.post('/api/admin/reset-demo',headers=PIN).json()['ok']
    data=client.get('/api/dashboard',headers=PIN).json()
    assert data['stats']['waiting']==6
