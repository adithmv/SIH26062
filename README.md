# SIH26062

A polar expedition operations prototype centered on a **Connectivity-Aware Mission Continuity Engine**. The current interface uses the working name **Polaris**.

## Status

Phase 1 foundation implemented: React navigation, read-only mission briefings, FastAPI, seven related database models, Alembic migrations, deterministic fictional fixtures, Docker Compose and CI checks.

Offline capture, mission editing, overdue rules, maps and priority synchronization are future phases. No satellite or live tracking hardware is connected.

## Start with Docker (recommended)

Install Docker Desktop with its Linux engine running. From the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Open [the application](http://localhost:5173) and [interactive API documentation](http://localhost:8000/docs).
Startup waits for PostgreSQL, applies migrations and loads additive demo fixtures before starting the web interface.

- Web: http://localhost:5173
- API health: http://localhost:8000/api/health
- OpenAPI: http://localhost:8000/openapi.json
- Logs: `docker compose logs -f`
- Stop while retaining data: `docker compose down`

Ports bind to your local machine. The supplied credentials are public local-demo defaults, not production secrets. Do not use real personnel data or expose this unauthenticated development stack publicly. URL-encode special characters if changing the password used in the database connection URL.

## Run without Docker

Requires Node.js 22.12+ and Python 3.12–3.14. This path uses a local SQLite demo database, not PostgreSQL.

Backend, from a PowerShell terminal:

```powershell
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m app.seed
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend, from a second terminal at the repository root:

```powershell
cd frontend
npm ci
npm run dev
```

On macOS/Linux, use `.venv/bin/python` instead. Set `DATABASE_URL` in the backend terminal to use an existing PostgreSQL database. The frontend development proxy forwards `/api` to port 8000; override `API_PROXY_TARGET` if needed. The backend does not automatically read a .env file; Compose reads the root .env.

## Verification

```powershell
cd backend
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m alembic check
cd ../frontend
npm run build
npm run lint
npx playwright install chromium
npx playwright test
```

Browser tests require the seeded API running on port 8000 and start Vite automatically. Backend tests use an isolated temporary SQLite database by default. Set `TEST_DATABASE_URL` **only to a disposable test database** for PostgreSQL tests: the suite applies and rolls back its schema. CI runs those tests against PostgreSQL 17.

## Repository

- `frontend/`: React, TypeScript, Vite and Tailwind interface.
- `backend/app/`: FastAPI, SQLAlchemy models and fictional fixtures.
- `backend/migrations/`: versioned schema changes.
- `compose.yaml`: local PostgreSQL, API and web services.
- [API and data contracts](docs/API.md).
- [Development phases](docs/ROADMAP.md).

## Demonstration data

Fixed snapshot: **28 September 2026**. Four fictional people, two missions, two vehicles, one simulated position, one radio check-in and one event. Names do not represent actual expedition members. Seed identifiers are deterministic UUIDs; running the seed again does not overwrite existing records.

Locations are last confirmed observations, never guaranteed current positions. Observation and receipt times are separate UTC values. Mission statuses in this phase are stored fixtures, not calculated safety assessments.

## Next milestone

Phase 2: mission creation and updates, field check-ins, position recording, overdue rules and mission completion.

## Phase 1 verification record

Verified locally: backend tests (3 passed), migration/model consistency, frontend build and lint, Edge browser smoke tests (3 passed), dashboard screenshot review, live API/proxy requests, and Compose configuration validation. Full Docker/PostgreSQL startup was not verified because the local Docker engine was unavailable. CI is configured to exercise PostgreSQL but its result must be checked on GitHub.

If downloaded Chromium cannot launch on Windows, run browser tests with `$env:PLAYWRIGHT_CHANNEL="msedge"` to use installed Edge.
