# Backend

For installation, follow the [main README](../README.md). For sign-in and HTTPS, use the [base station guide](../docs/BASE_STATION.md).

## Find the code

| File in `app/` | Purpose |
| --- | --- |
| `main.py`, `operations.py` | API routes and mission rules |
| `logistics.py` | Cargo, equipment, inventory and alerts |
| `files.py`, `storage_check.py` | File storage, encryption and integrity checks |
| `connections.py` | Backend connection checks |
| `pmce.py`, `pmce_worker.py` | Event queue and delivery |
| `ingestion.py`, `transport.py` | Receive and process events |
| `security.py`, `accounts.py`, `devices.py` | Sign-in, permissions and device credentials |
| `models.py`, `db.py` | Database tables and connections |
| `schemas.py`, `event_schemas.py` | Input and response formats |
| `config.py`, `base.py` | Settings and base status |

Database upgrades are in `migrations/`. Tests are in `tests/`.

## Local API

Use the installation commands in the main README. Open http://127.0.0.1:8000/docs for interactive API documentation in local mode. Base mode disables that page. Default database: `operations.sqlite3`. Fresh installations are empty.

Create personnel and vehicles first, then plan a mission. Register equipment, cargo and stock; assign/link them before departure. Stock starts at zero; enter the opening balance as an inventory adjustment.

## Start field API

After starting the local API, open another PowerShell window in `backend/` and run:

```powershell
$env:DATABASE_URL = "sqlite:///./field.sqlite3"
$env:PMCE_CENTRAL_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
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
.\.venv\Scripts\python.exe -m app.pmce_worker --mode limited --interval 5 --byte-budget 2048 --compression
```

Stop with Ctrl+C. Restart with a different mode as needed. Each pass has its own budget. A shared lease prevents overlapping passes; crashed leases expire within 15 minutes.

## APIs

See [mission endpoints](../docs/API.md), [file management](../docs/DATA_MANAGEMENT.md) and [PMCE events](../docs/PMCE.md).

Payload fields and priorities: [event contract](../docs/PMCE.md). These delivery modes are policies, not network simulations. For a deployed base, use its HTTPS address and an authorized device credential as described in the [base setup guide](../docs/BASE_STATION.md).

## Verification and limits

From this folder, run `.\.venv\Scripts\python.exe -m pytest -q`. Tests use isolated databases only.

Delivery policies do not measure satellite bandwidth. Byte counts exclude HTTP overhead. Maximum event/request size is 64 KiB, including after decompression. Large event attachments are not supported. Receipts confirm database commit; operator SOS acknowledgement is separate. Browser delivery is separate from the field-service queue. Base mode supports sign-in and device credentials; local mode has no sign-in. Real emergency dispatch and the remote file-transfer interface are not implemented.
