from uuid import UUID, uuid4
from datetime import timedelta

import httpx
from sqlalchemy.orm import Session

from app.models import PMCEOutbox
from app import pmce


def event(kind="sos", **changes):
    return {"id": str(uuid4()), "device_id": "field-01", "mission_id": str(uuid4()),
            "kind": kind, "occurred_at": "2026-10-01T12:00:00Z",
            "payload": {"message": "Test event"}, **changes}


def test_policy_and_durable_queue(client, database):
    routine, safety, sos = event("report"), event("check_in"), event()
    for body in (routine, safety, sos):
        assert client.post("/api/pmce/outbox", json=body).status_code == 201
    with Session(database) as session:
        assert session.get(PMCEOutbox, UUID(sos["id"])) is not None
    offline = client.post("/api/pmce/plan", json={"mode": "offline"}).json()
    assert all(row["action"] == "queue" for row in offline)
    assert [row["id"] for row in offline] == [sos["id"], safety["id"], routine["id"]]
    budget = len(pmce.encode(sos))
    limited = client.post("/api/pmce/plan", json={"mode": "limited", "byte_budget": budget}).json()
    assert [row["action"] for row in limited] == ["send", "queue", "queue"]
    assert "budget" in limited[1]["reason"]
    broadband = client.post("/api/pmce/plan", json={"mode": "broadband"}).json()
    assert all(row["action"] == "send" for row in broadband)
    assert client.get("/api/pmce/outbox").json()[0]["attempts"] == 0


def test_receipts_are_idempotent_and_immutable(client):
    body = event()
    for path in ("/api/pmce/outbox", "/api/pmce/events"):
        assert client.post(path, json=body).is_success
        assert client.post(path, json=body).is_success
        assert len(client.get(path).json()) == 1
        assert client.post(path, json={**body, "payload": {"message": "Changed"}}).status_code == 409


def test_validation(client):
    for changes in ({"kind": "unknown"}, {"priority": 0},
                    {"occurred_at": "2026-10-01T12:00:00"},
                    {"payload": {"data": "a" * 65536}}):
        assert client.post("/api/pmce/outbox", json=event(**changes)).status_code == 422
    assert client.post("/api/pmce/sync", json={"mode": "limited", "byte_budget": 0}).status_code == 422


def mock_central(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setenv("PMCE_CENTRAL_URL", "http://central.test")
    monkeypatch.setattr(pmce.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def test_offline_does_not_transmit_and_limited_defers_routine(client, monkeypatch):
    bodies = [event("report"), event()]
    for body in bodies:
        client.post("/api/pmce/outbox", json=body)
    sent = []

    def central(request):
        import json
        body = json.loads(request.content)
        sent.append(body["id"])
        return httpx.Response(200, json={"acknowledged_event_id": body["id"]})

    mock_central(monkeypatch, central)
    client.post("/api/pmce/sync", json={"mode": "offline"})
    assert sent == []
    client.post("/api/pmce/sync", json={"mode": "limited"})
    assert sent == [bodies[1]["id"]]
    client.post("/api/pmce/sync", json={"mode": "broadband"})
    assert sent == [bodies[1]["id"], bodies[0]["id"]]
    assert all(row["status"] == "acknowledged" for row in client.get("/api/pmce/outbox").json())
    assert client.post("/api/pmce/sync", json={"mode": "broadband"}).json() == []


def test_lost_receipt_retries_without_duplicate_central_event(client, monkeypatch):
    import json
    body = event()
    client.post("/api/pmce/outbox", json=body)
    calls = 0

    def central(request):
        nonlocal calls
        calls += 1
        receipt = client.post("/api/pmce/events", json=json.loads(request.content))
        if calls == 1:
            raise httpx.ReadTimeout("Receipt lost", request=request)
        return httpx.Response(200, json=receipt.json())

    mock_central(monkeypatch, central)
    first = client.post("/api/pmce/sync", json={"mode": "broadband"})
    assert first.json()[0]["status"] == "pending"
    assert len(client.get("/api/pmce/events").json()) == 1
    later = pmce.now_utc() + timedelta(seconds=6)
    monkeypatch.setattr(pmce, "now_utc", lambda: later)
    second = client.post("/api/pmce/sync", json={"mode": "broadband"})
    assert second.json()[0]["status"] == "acknowledged"
    assert len(client.get("/api/pmce/events").json()) == 1
    row = client.get("/api/pmce/outbox").json()[0]
    assert row["attempts"] == 2
    assert row["last_error"] is None


def test_wrong_receipt_keeps_event_pending(client, monkeypatch):
    client.post("/api/pmce/outbox", json=event())
    mock_central(monkeypatch, lambda request: httpx.Response(200, json={"acknowledged_event_id": str(uuid4())}))
    assert client.post("/api/pmce/sync", json={"mode": "broadband"}).json()[0]["status"] == "pending"
    assert client.get("/api/pmce/outbox").json()[0]["acknowledged_at"] is None


def test_backoff_pause_and_explicit_retry(client, monkeypatch):
    body = event()
    client.post("/api/pmce/outbox", json=body)
    clock = pmce.now_utc()
    monkeypatch.setattr(pmce, "now_utc", lambda: clock)
    calls = []

    def unavailable(request):
        calls.append(request)
        return httpx.Response(503)

    mock_central(monkeypatch, unavailable)
    for attempt in range(5):
        result = client.post("/api/pmce/sync", json={"mode": "broadband"})
        assert result.status_code == 200
        assert len(calls) == attempt + 1
        assert client.post("/api/pmce/sync", json={"mode": "broadband"}).json() == []
        clock += timedelta(seconds=61)
    row = client.get("/api/pmce/outbox").json()[0]
    assert row["status"] == "paused"
    assert row["attempts"] == 5
    assert client.post("/api/pmce/sync", json={"mode": "broadband"}).json() == []
    assert client.get("/api/pmce/status").json()["counts"]["paused"] == 1
    retry = client.post(f'/api/pmce/outbox/{body["id"]}/retry')
    assert retry.json()["status"] == "pending"
    assert retry.json()["attempts"] == 5
    assert retry.json()["event"] == body


def test_rejected_event_does_not_block_following_work(client, monkeypatch):
    import json
    bad, good = event(), event("check_in")
    for body in (bad, good):
        client.post("/api/pmce/outbox", json=body)

    def central(request):
        body = json.loads(request.content)
        if body["id"] == bad["id"]:
            return httpx.Response(409)
        return httpx.Response(200, json={"acknowledged_event_id": body["id"]})

    mock_central(monkeypatch, central)
    result = client.post("/api/pmce/sync", json={"mode": "broadband"}).json()
    assert [row["status"] for row in result] == ["blocked", "acknowledged"]
    state = client.get("/api/pmce/status").json()
    assert state["counts"] == {"blocked": 1, "acknowledged": 1, "pending": 0, "paused": 0}
    assert state["undelivered_by_priority"]["P0"] == 1
    assert state["attempts"] == 2
    assert len(client.get("/api/pmce/outbox?pending_only=true").json()) == 1
    assert client.post(f'/api/pmce/outbox/{good["id"]}/retry').status_code == 409


def test_sync_lease_prevents_overlap_and_recovers_after_expiry(client, database, monkeypatch):
    with Session(database) as session:
        owner = pmce.acquire_sync(session)
    assert client.post("/api/pmce/sync", json={"mode": "offline"}).status_code == 409
    later = pmce.now_utc() + timedelta(seconds=pmce.LEASE_SECONDS + 1)
    monkeypatch.setattr(pmce, "now_utc", lambda: later)
    with Session(database) as session:
        new_owner = pmce.acquire_sync(session)
        pmce.release_sync(session, owner)
    assert client.post("/api/pmce/sync", json={"mode": "offline"}).status_code == 409
    with Session(database) as session:
        pmce.release_sync(session, new_owner)
    assert client.post("/api/pmce/sync", json={"mode": "offline"}).status_code == 200


def test_sync_releases_lease_after_configuration_failure(client, monkeypatch):
    monkeypatch.delenv("PMCE_CENTRAL_URL", raising=False)
    client.post("/api/pmce/outbox", json=event())
    assert client.post("/api/pmce/sync", json={"mode": "broadband"}).status_code == 503
    assert client.post("/api/pmce/sync", json={"mode": "offline"}).status_code == 200


def test_waiting_event_does_not_hide_due_event_at_batch_limit(client, monkeypatch):
    client.post("/api/pmce/outbox", json=event())
    mock_central(monkeypatch, lambda request: httpx.Response(429))
    assert client.post("/api/pmce/sync", json={"mode": "broadband"}).json()[0]["status"] == "pending"
    safety = event("check_in")
    client.post("/api/pmce/outbox", json=safety)
    result = client.post("/api/pmce/plan", json={"mode": "broadband", "limit": 1}).json()
    assert result[0]["id"] == safety["id"]
