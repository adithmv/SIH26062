# SIH26062

Polar expedition operations with an offline-first PMCE backend.

## Backend status

- Phase 1: persistent queue, priorities, retries, sync worker and receipts.
- Phase 2: validated check-ins, positions, SOS alerts and mission history.
- Phase 3: equipment, cargo, stock movements and mission impact view.

All three backend phases are implemented. The existing frontend covers mission operations; the new logistics and PMCE APIs are available through `/docs`.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000/docs. A fresh database contains no operational records. Enter your own data through the API. No startup seeding is performed.

For the existing frontend, run `npm ci` and `npm run dev` from `frontend`. Docker setup: `docker compose up --build`.

## Details

- [Backend setup and sync](backend/README.md)
- [PMCE event contract](docs/PMCE.md)
- [Existing mission API](docs/API.md)
- [Project roadmap](docs/ROADMAP.md)

## Tests

Run `python -m pytest -q` from `backend`. Tests use disposable databases; fixture data stays inside tests. Set `TEST_DATABASE_URL` only to a disposable database: tests migrate and roll back its schema.

Existing local databases and browser caches are not erased. The default local database is now `operations.sqlite3`; an explicit `DATABASE_URL` continues using the selected database.

## Scope

This is a prototype backend. Connection profiles are caller-controlled. Authentication, authorization, real communication gateways, large-file transfers and field validation remain outside these three backend phases. Keep the service on localhost until access controls are added.
