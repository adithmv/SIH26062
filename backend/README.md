# PMCE backend

Basic persistent event queue and priority-based sync. Uses the existing FastAPI backend.

## Run (PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000/docs. This instance receives central events.

For a separate field instance, open another terminal in `backend`, activate the venv, then run:

```powershell
$env:DATABASE_URL = "sqlite:///./field.sqlite3"
$env:PMCE_CENTRAL_URL = "http://127.0.0.1:8000"
alembic upgrade head
uvicorn app.main:app --port 8001
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| POST / GET | `/api/pmce/outbox` | Save / list field events |
| POST | `/api/pmce/plan` | Preview send/queue decisions |
| POST | `/api/pmce/sync` | Attempt delivery to central |
| POST | `/api/pmce/outbox/{id}/retry` | Reset failed delivery for another attempt |
| GET | `/api/pmce/status` | Queue counts, priorities and attempts |
| POST / GET | `/api/pmce/events` | Receive / list central events |

Example outbox body (use a new UUID for each event):

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "device_id": "field-01",
  "mission_id": "22222222-2222-4222-8222-222222222222",
  "kind": "sos",
  "occurred_at": "2026-10-01T12:00:00Z",
  "payload": {"message": "Need assistance"}
}
```

Plan/sync body: `{"mode":"limited","byte_budget":2048,"limit":100}`.

- P0: `sos`. P1: `check_in`, `position`. P2: `critical_inventory`, `vehicle_status`.
- P3: `inventory_update`, `mission_log`. P4: `report`.
- Offline queues everything. Limited sends P0-P2 within a per-call JSON byte budget. Broadband sends all priorities, up to `limit`.
- Equal priorities use queue time. Events over the remaining budget wait. Maximum event size: 64 KiB.
- Matching central receipts mark delivery. Lost receipts can be retried safely. Reusing an ID with different contents returns 409.
- Temporary failures retry after 5, 10, 20, 40, then 60 seconds; five failures pause the event. Permanent HTTP 4xx rejections (except 408/429) block it. Explicit retry resets delivery state, preserving the event and total attempts.
- Plan lists only due, unblocked events. Outbox supports `pending_only=true`, `offset` and `limit`.

## Automatic delivery

Run in a third terminal using the field database and central URL above:

```powershell
python -m app.pmce_worker --mode limited --interval 5 --byte-budget 2048
```

Stop with Ctrl+C. Restart with `--mode broadband` to drain routine events. Default mode is offline. API and worker share one sync lease; overlapping passes return 409. After a crash, the lease expires within 15 minutes. Each pass gets its own byte budget.

## Demo

Queue a report and an SOS on port 8001. Sync offline: both stay pending. Sync limited: SOS reaches port 8000 first. Sync broadband: the report follows. Check both event lists.

## Limits

First temporary failure stops the pass; blocked events do not stop other work. Modes are supplied by the caller, not measured. Budget excludes HTTP overhead and responses. No compression, attachments or authentication. Receipt means stored centrally, not acknowledged by an operator. Events are stored only; existing mission/inventory records and frontend are not updated. The field service must run locally to accept events without central connectivity.

## Backend phases

1. Reliable delivery: implemented (queue, priorities, retries, worker, sync lease, status).
2. Mission integration: next (validate payloads; apply received check-ins, positions and SOS).
3. Cargo/inventory: planned (mission-linked assets and stock movements).

These are backend work steps, not the full project roadmap phases.

## Test

```powershell
python -m pytest -q
```
