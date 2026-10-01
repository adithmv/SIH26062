# PMCE backend

## Start central API

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000/docs. Default database: `operations.sqlite3`. Fresh installations are empty. No sample data is loaded.

Create personnel and vehicles first, then plan a mission. Register equipment, cargo and stock; assign/link them before departure. Stock starts at zero; enter the opening balance as an inventory adjustment.

## Start field API

In another terminal, activate the same environment and run:

```powershell
$env:DATABASE_URL = "sqlite:///./field.sqlite3"
$env:PMCE_CENTRAL_URL = "http://127.0.0.1:8000"
alembic upgrade head
uvicorn app.main:app --port 8001
```

Capture field events through `/api/pmce/outbox`, using actual central mission/resource IDs. This endpoint persists locally without contacting central. Central receipt and operational changes commit together.

## Delivery

Call `/api/pmce/sync` with `mode`, optional `byte_budget`, `limit` and `compression`. Modes: `offline`, `limited`, `broadband`. Compression defaults to false.

- Offline sends nothing.
- Limited sends P0-P2 within the outgoing payload budget.
- Broadband sends all priorities, up to the batch limit.
- Optional gzip is used only when smaller. Budget counts transmitted payload bytes.
- Temporary failures back off; five failures pause delivery. Other HTTP 4xx responses block the event, except 408/429.
- Retry unchanged events with `/outbox/{id}/retry`. For stock/cargo conflicts, review central state and use `/outbox/{id}/resolve` with a new UUID and reviewed version. Original records remain visible.

For automatic passes, run in a third terminal with the same field database and central URL:

```powershell
python -m app.pmce_worker --mode limited --interval 5 --byte-budget 2048 --compression
```

Stop with Ctrl+C. Restart with a different mode as needed. Each pass has its own budget. A shared lease prevents overlapping passes; crashed leases expire within 15 minutes.

## APIs

| Path (under `/api`) | Purpose |
| --- | --- |
| `personnel`, `vehicles` | Create/list operational resources |
| `missions` | Plan, depart, observe and complete missions |
| `assets`, `assets/{id}/assignment` | Register/assign equipment |
| `cargo` | Register/list mission cargo |
| `inventory`, `inventory/adjustments` | Register stock and record opening/corrective balances |
| `inventory/{id}/movements` | Stock ledger |
| `missions/{id}/supplies/{item_id}` | Link supplies before departure |
| `missions/{id}/impact` | Personnel, vehicle, equipment, cargo, stock and alerts |
| `alerts`, `alerts/{id}/acknowledge`, `alerts/{id}/resolve` | Operator SOS workflow |
| `pmce/outbox`, `pmce/plan`, `pmce/sync` | Capture, preview and transmit |
| `pmce/events`, `pmce/status` | Central history and queue metrics |

Payload fields and priorities: [event contract](../docs/PMCE.md). Interactive schemas: `/docs`.

## Verification and limits

Run `python -m pytest -q`. Tests use isolated databases only. All three backend phases are implemented and covered by tests.

Profiles do not measure satellite bandwidth. Byte counts exclude HTTP overhead. Maximum event/request size is 64 KiB, including after decompression. Large attachments are not supported. Receipts confirm database commit; operator SOS acknowledgement is separate. Logs/reports are retained in event history. Existing frontend delivery is separate from the field-service PMCE queue. No authentication or real emergency dispatch integration is included.
