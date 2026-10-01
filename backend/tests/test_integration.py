"""Operational integration uses only disposable test databases."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Event, PMCEReceipt
from app import pmce

pytestmark = pytest.mark.empty_database


def post(client, path, body):
    response = client.post(path, json=body)
    assert response.is_success, response.text
    return response.json()


def setup_mission(client):
    person = post(client, "/api/personnel", {"name": "Test operator", "role": "Test", "station": "Test station"})
    vehicle = post(client, "/api/vehicles", {"code": uuid4().hex[:8], "kind": "Test vehicle"})
    now = datetime.now(timezone.utc)
    mission = post(client, "/api/missions", {
        "code": uuid4().hex[:8], "name": "Test mission", "destination": "Test destination", "station": "Test station",
        "vehicle_id": vehicle["id"], "personnel_ids": [person["id"]],
        "departure": now.isoformat(), "expected_check_in": (now + timedelta(hours=1)).isoformat(),
        "expected_return": (now + timedelta(hours=4)).isoformat(),
    })
    return mission, vehicle


def depart(client, mission):
    current = client.get("/api/missions/" + mission["id"]).json()
    return post(client, f'/api/missions/{mission["id"]}/depart', {"version": current["version"]})


def event(mission, kind, payload, **changes):
    return {"id": str(uuid4()), "mission_id": mission["id"], "device_id": "test-device", "kind": kind,
            "occurred_at": datetime.now(timezone.utc).isoformat(), "payload": payload, **changes}


def ingest(client, mission, kind, payload, **changes):
    body = event(mission, kind, payload, **changes)
    return body, post(client, "/api/pmce/events", body)


def test_fresh_database_is_empty(client):
    for path in ("missions", "personnel", "vehicles", "assets", "cargo", "inventory", "alerts", "events", "pmce/events", "pmce/outbox"):
        assert client.get("/api/" + path).json() == []
    assert client.get("/api/pmce/status").json()["central_events"] == 0


def test_real_input_to_mission_observations_and_sos(client, database):
    mission, vehicle = setup_mission(client)
    mission = depart(client, mission)
    body, receipt = ingest(client, mission, "check_in", {"source": "radio", "note": "Contact received"})
    assert receipt["acknowledged_event_id"] == body["id"]
    post(client, "/api/pmce/events", body)
    current = client.get("/api/missions/" + mission["id"]).json()
    assert len(current["check_ins"]) == 1
    assert current["version"] == mission["version"] + 1
    old_time = datetime.now(timezone.utc).isoformat()
    ingest(client, mission, "position", {"source": "gnss", "latitude": 10, "longitude": 20})
    ingest(client, mission, "position", {"source": "gnss", "latitude": 1, "longitude": 2}, occurred_at=old_time)
    current = client.get("/api/missions/" + mission["id"]).json()
    assert current["last_position"]["latitude"] == 10
    sos, _ = ingest(client, mission, "sos", {"message": "Test emergency"})
    current = client.get("/api/missions/" + mission["id"]).json()
    assert current["escalation_level"] == "emergency"
    assert client.post(f'/api/missions/{mission["id"]}/complete', json={"version": current["version"], "note": "Return"}).status_code == 409
    assert client.post(f'/api/missions/{mission["id"]}/escalation', json={"version": current["version"], "level": "none", "reason": "Clear"}).status_code == 409
    alert = client.get("/api/alerts?open_only=true").json()[0]
    assert alert["acknowledged_at"] is None
    action = {"version": alert["version"], "operator": "Test operator", "note": "Responding"}
    assert client.post(f'/api/alerts/{sos["id"]}/resolve', json=action).status_code == 409
    ack = post(client, f'/api/alerts/{sos["id"]}/acknowledge', action)
    post(client, f'/api/alerts/{sos["id"]}/resolve', {**action, "version": ack["version"], "note": "Resolved"})
    assert client.get("/api/alerts?open_only=true").json() == []
    current = client.get("/api/missions/" + mission["id"]).json()
    post(client, f'/api/missions/{mission["id"]}/complete', {"version": current["version"], "note": "Returned"})
    post(client, "/api/pmce/events", sos)  # Lost-receipt replay after mission completion.
    assert len(client.get("/api/alerts").json()) == 1
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(PMCEReceipt)) == 4


def test_invalid_events_have_no_partial_effects(client):
    mission, _ = setup_mission(client)
    mission = depart(client, mission)
    for kind, payload in (("position", {"source": "gnss", "latitude": 91, "longitude": 0}),
                          ("check_in", {"source": "radio", "note": ""}), ("sos", {"message": "SOS", "extra": True})):
        assert client.post("/api/pmce/events", json=event(mission, kind, payload)).status_code == 422
    unknown = event({"id": str(uuid4())}, "sos", {"message": "Missing mission"})
    assert client.post("/api/pmce/events", json=unknown).status_code == 404
    future = event(mission, "sos", {"message": "Future"}, occurred_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    assert client.post("/api/pmce/events", json=future).status_code == 422
    assert client.get("/api/pmce/events").json() == []
    assert client.get("/api/missions/" + mission["id"]).json()["version"] == mission["version"]


def prepare_logistics(client, mission):
    asset = post(client, "/api/assets", {"code": "TEST-ASSET", "name": "Test instrument"})
    response = client.put(f'/api/assets/{asset["id"]}/assignment', json={"version": asset["version"], "mission_id": mission["id"]})
    assert response.is_success, response.text
    cargo = post(client, "/api/cargo", {"code": "TEST-CARGO", "description": "Test equipment", "mission_id": mission["id"], "location": "Test station"})
    item = post(client, "/api/inventory", {"sku": "TEST-STOCK", "name": "Test supply", "unit": "units", "station": "Test station", "critical": True})
    assert item["quantity"] == 0
    movement = {"id": str(uuid4()), "item_id": item["id"], "expected_version": item["version"], "delta": 10,
                "note": "Test opening count", "occurred_at": datetime.now(timezone.utc).isoformat()}
    post(client, "/api/inventory/adjustments", movement)
    post(client, "/api/inventory/adjustments", movement)
    assert client.put(f'/api/missions/{mission["id"]}/supplies/{item["id"]}').is_success
    return asset, cargo, client.get("/api/inventory").json()[0]


def test_logistics_versions_stock_and_history(client):
    mission, vehicle = setup_mission(client)
    asset, cargo, item = prepare_logistics(client, mission)
    mission = depart(client, mission)
    body, _ = ingest(client, mission, "critical_inventory", {"item_id": item["id"], "expected_version": item["version"], "delta": -3, "note": "Issued"})
    post(client, "/api/pmce/events", body)
    stock = client.get("/api/inventory").json()[0]
    assert stock["quantity"] == 7
    assert len(client.get(f'/api/inventory/{item["id"]}/movements').json()) == 2
    stale = {**body, "id": str(uuid4())}
    assert client.post("/api/pmce/events", json=stale).status_code == 409
    too_much = {**stale, "payload": {**body["payload"], "expected_version": stock["version"], "delta": -8}}
    assert client.post("/api/pmce/events", json=too_much).status_code == 409
    wrong_priority = {**stale, "kind": "inventory_update", "payload": {**body["payload"], "expected_version": stock["version"]}}
    assert client.post("/api/pmce/events", json=wrong_priority).status_code == 422
    assert client.get("/api/inventory").json()[0]["quantity"] == 7
    ingest(client, mission, "asset_condition", {"asset_id": asset["id"], "condition": "maintenance", "note": "Needs inspection"})
    ingest(client, mission, "vehicle_status", {"vehicle_id": vehicle["id"], "condition": "operational", "note": "Checked"})
    for status in ("loaded", "in_transit", "delivered"):
        body, _ = ingest(client, mission, "cargo_movement", {"cargo_id": cargo["id"], "expected_version": cargo["version"],
                                "status": status, "location": "Test location", "note": "Test movement"})
        post(client, "/api/pmce/events", body)
        cargo = client.get("/api/cargo").json()[0]
        assert cargo["status"] == status
    impact = client.get(f'/api/missions/{mission["id"]}/impact').json()
    assert impact["assets"][0]["condition"] == "maintenance"
    assert impact["mission"]["vehicle"]["condition"] == "operational"
    assert impact["cargo"][0]["status"] == "delivered"
    assert impact["supplies"][0]["quantity"] == 7


def test_full_offline_limited_broadband_sync(client, monkeypatch):
    import httpx
    import json
    mission, _ = setup_mission(client)
    depart(client, mission)
    report = event(mission, "report", {"title": "Test report", "text": "Test body"})
    sos = event(mission, "sos", {"message": "Test emergency"})
    for body in (report, sos):
        post(client, "/api/pmce/outbox", body)
    real_client = httpx.Client
    sent = []

    def central(request):
        body = json.loads(request.content)
        sent.append(body["kind"])
        response = client.post("/api/pmce/events", json=body)
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setenv("PMCE_CENTRAL_URL", "http://central.test")
    monkeypatch.setattr(pmce.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(central), **kwargs))
    post(client, "/api/pmce/sync", {"mode": "offline"})
    assert sent == []
    post(client, "/api/pmce/sync", {"mode": "limited"})
    assert sent == ["sos"]
    assert len(client.get("/api/alerts").json()) == 1
    post(client, "/api/pmce/sync", {"mode": "broadband"})
    assert sent == ["sos", "report"]
    assert client.get("/api/pmce/status").json()["counts"]["acknowledged"] == 2


def test_gzip_ingestion_and_size_limits(client):
    import gzip
    import json
    mission, _ = setup_mission(client)
    depart(client, mission)
    body = event(mission, "report", {"title": "Test", "text": "compressed content " * 100})
    headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}
    response = client.post("/api/pmce/events", content=gzip.compress(json.dumps(body).encode()), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["acknowledged_event_id"] == body["id"]
    assert client.post("/api/pmce/events", content=gzip.compress(b"x" * 70000), headers=headers).status_code == 413
    assert client.post("/api/pmce/events", content=b"invalid", headers=headers).status_code == 400
    assert client.post("/api/pmce/events", content=b"x" * 65537, headers={"Content-Type": "application/json"}).status_code == 413
    assert client.post("/api/pmce/events", content=b"x", headers={**headers, "Content-Encoding": "br"}).status_code == 415
    assert len(client.get("/api/pmce/events").json()) == 1


def test_reviewed_stock_conflict_keeps_original_and_applies_once(client, monkeypatch):
    import httpx
    import json
    mission, _ = setup_mission(client)
    _, _, item = prepare_logistics(client, mission)
    depart(client, mission)
    body = event(mission, "critical_inventory", {"item_id": item["id"], "expected_version": 1, "delta": -2, "note": "Test issue"})
    post(client, "/api/pmce/outbox", body)
    real_client = httpx.Client

    def central(request):
        response = client.post("/api/pmce/events", json=json.loads(request.content))
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setenv("PMCE_CENTRAL_URL", "http://central.test")
    monkeypatch.setattr(pmce.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(central), **kwargs))
    first = post(client, "/api/pmce/sync", {"mode": "broadband"})
    assert first[0]["status"] == "blocked"
    assert client.get("/api/inventory").json()[0]["quantity"] == 10
    reviewed = {**body, "id": str(uuid4()), "payload": {**body["payload"], "expected_version": item["version"]}}
    path = f'/api/pmce/outbox/{body["id"]}/resolve'
    assert client.post(path, json={**reviewed, "payload": {**reviewed["payload"], "delta": -5}}).status_code == 422
    replacement = post(client, path, reviewed)
    assert post(client, path, reviewed)["event"] == replacement["event"]
    result = post(client, "/api/pmce/sync", {"mode": "broadband"})
    assert len(result) == 1 and result[0]["status"] == "acknowledged"
    assert client.get("/api/inventory").json()[0]["quantity"] == 8
    state = client.get("/api/pmce/status").json()
    assert state["counts"]["superseded"] == 1
    assert state["counts"]["acknowledged"] == 1
    assert state["payload_bytes_attempted"] > state["payload_bytes_acknowledged"] > 0


def test_separate_field_database_compressed_delivery(client, monkeypatch, tmp_path):
    import httpx
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from app.db import Base, get_session
    from app.models import PMCESyncLock

    mission, _ = setup_mission(client)
    depart(client, mission)
    field_engine = create_engine("sqlite:///" + (tmp_path / "field.sqlite3").as_posix())
    Base.metadata.create_all(field_engine)
    with Session(field_engine) as session:
        session.add(PMCESyncLock(id=1))
        session.commit()
    field_app = FastAPI()
    field_app.include_router(pmce.router)

    def field_session():
        with Session(field_engine) as session:
            yield session

    field_app.dependency_overrides[get_session] = field_session
    real_client = httpx.Client
    encoding_used = []

    def central(request):
        encoding_used.append(request.headers["Content-Encoding"])
        response = client.post("/api/pmce/events", content=request.content,
                               headers={"Content-Type": "application/json", "Content-Encoding": request.headers["Content-Encoding"]})
        return httpx.Response(response.status_code, json=response.json())

    monkeypatch.setenv("PMCE_CENTRAL_URL", "http://central.test")
    monkeypatch.setattr(pmce.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(central), **kwargs))
    try:
        with TestClient(field_app) as field:
            body = event(mission, "sos", {"message": "Need assistance. " * 20})
            post(field, "/api/pmce/outbox", body)
            assert client.get("/api/pmce/outbox").json() == []
            assert field.get("/api/pmce/events").json() == []
            decision = post(field, "/api/pmce/plan", {"mode": "limited", "compression": True})[0]
            assert decision["bytes"] < decision["original_bytes"]
            post(field, "/api/pmce/sync", {"mode": "limited", "compression": True, "byte_budget": decision["bytes"]})
            assert encoding_used == ["gzip"]
            assert field.get("/api/pmce/outbox").json()[0]["status"] == "acknowledged"
            assert client.get("/api/alerts").json()[0]["id"] == body["id"]
    finally:
        field_engine.dispose()


def test_wrong_mission_resources_and_stale_alert_actions(client):
    mission, vehicle = setup_mission(client)
    asset, cargo, item = prepare_logistics(client, mission)
    other, other_vehicle = setup_mission(client)
    depart(client, other)
    payloads = (
        ("asset_condition", {"asset_id": asset["id"], "condition": "maintenance", "note": "Test"}),
        ("vehicle_status", {"vehicle_id": vehicle["id"], "condition": "maintenance", "note": "Test"}),
        ("cargo_movement", {"cargo_id": cargo["id"], "expected_version": 1, "status": "loaded", "location": "Test", "note": "Test"}),
        ("critical_inventory", {"item_id": item["id"], "expected_version": item["version"], "delta": -1, "note": "Test"}),
    )
    for kind, payload in payloads:
        assert client.post("/api/pmce/events", json=event(other, kind, payload)).status_code == 422
    assert client.get("/api/pmce/events").json() == []
    sos, _ = ingest(client, other, "sos", {"message": "Test"})
    action = {"version": 1, "operator": "Test", "note": "Responding"}
    post(client, f'/api/alerts/{sos["id"]}/acknowledge', action)
    assert client.post(f'/api/alerts/{sos["id"]}/resolve', json=action).status_code == 409
    assert client.get("/api/alerts").json()[0]["resolved_at"] is None


def test_condition_late_delivery_and_assignment_lock(client):
    mission, vehicle = setup_mission(client)
    asset, _, _ = prepare_logistics(client, mission)
    depart(client, mission)
    earlier = datetime.now(timezone.utc).isoformat()
    ingest(client, mission, "asset_condition", {"asset_id": asset["id"], "condition": "maintenance", "note": "Latest"})
    ingest(client, mission, "asset_condition", {"asset_id": asset["id"], "condition": "operational", "note": "Older"}, occurred_at=earlier)
    current = client.get("/api/assets").json()[0]
    assert current["condition"] == "maintenance"
    assert client.put(f'/api/assets/{asset["id"]}/assignment', json={"version": current["version"], "mission_id": None}).status_code == 409
    assert client.get("/api/assets").json()[0]["mission_id"] == mission["id"]


def test_concurrent_stock_updates_cannot_overspend(client):
    from concurrent.futures import ThreadPoolExecutor
    mission, _ = setup_mission(client)
    _, _, item = prepare_logistics(client, mission)
    depart(client, mission)
    requests = [event(mission, "critical_inventory", {"item_id": item["id"], "expected_version": item["version"], "delta": -7, "note": "Concurrent test"}) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda body: client.post("/api/pmce/events", json=body), requests))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert client.get("/api/inventory").json()[0]["quantity"] == 3
    assert len(client.get("/api/pmce/events").json()) == 1
