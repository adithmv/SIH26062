# SIH26062

A polar expedition operations prototype centered on a **Connectivity-Aware Mission Continuity Engine**. The current interface uses the working name **Polaris**.

## Status

Phases 1–3 implemented. Phase 2 provides: mission planning and editing, personnel/vehicle assignments, departure, check-ins, position recording and maps, configurable overdue-contact rules, explicit operator escalation and team return. The Phase 1 API, migrations, demo fixtures, Compose setup and CI remain in place.

Phase 3 adds a cached app shell, saved mission packs, atomic local check-ins/positions, delivery history and safe manual delivery. Priority-based synchronization remains Phase 4. No live tracking hardware or emergency dispatch is connected. A bounded coordinate grid works offline; the optional online basemap requires internet.

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
npm run build
npm run preview -- --port 5173
```

On macOS/Linux, use `.venv/bin/python` instead. Set `DATABASE_URL` in the backend terminal to use an existing PostgreSQL database. The frontend proxy forwards `/api` to port 8000; override `API_PROXY_TARGET` if needed. The backend does not automatically read a .env file; Compose reads the root .env.

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

Browser tests WRITE fictional missions and move the seeded FM-002 plan into the past. Run them only against a disposable seeded API, not a database you want to preserve. They build the PWA and start a dedicated production preview on port 5175. Tests run serially against shared fictional resources. For an isolated local run, start a second backend terminal with DATABASE_URL set to sqlite:///./browser-tests.sqlite3, run migrations and seeding, then start Uvicorn on port 8001. Set API_PROXY_TARGET to http://127.0.0.1:8001 in the frontend test terminal. CI uses its disposable PostgreSQL database. Backend tests use an isolated temporary SQLite database by default. Set `TEST_DATABASE_URL` **only to a disposable test database** for PostgreSQL tests: the suite applies and rolls back its schema. CI runs those tests against PostgreSQL 17.

## Repository

- `frontend/`: React, TypeScript, Vite and Tailwind interface.
- `backend/app/`: FastAPI, SQLAlchemy models and fictional fixtures.
- `backend/migrations/`: versioned schema changes.
- `compose.yaml`: local PostgreSQL, API and web services.
- [API and data contracts](docs/API.md).
- [Offline setup, behavior and limits](docs/OFFLINE.md).
- [Development phases](docs/ROADMAP.md).

## Demonstration data

Fixed snapshot: **28 September 2026**. Four fictional people, two missions, two vehicles, one simulated position, one radio check-in and one event. Names do not represent actual expedition members. Seed identifiers are deterministic UUIDs; running the seed again does not overwrite existing records.

Locations are last confirmed observations, never guaranteed current positions. Observation and receipt times are separate UTC values. Lifecycle starts from the fixtures, while contact and return status are evaluated against the server clock. Old fixtures can therefore be overdue. These are operational prompts, not guarantees of safety.

## Next milestone

Phase 4: connectivity profiles, priority scheduling, bandwidth budgets, automatic reconnection delivery and conflict resolution.

## Phase 3 verification record

Verified locally: backend tests (15 passed), migration/model consistency, frontend build and lint, Edge browser tests (9 passed), offline mission and mobile planning screenshot review, live API/proxy requests, and Compose configuration validation. Full Docker/PostgreSQL startup was not verified because the local Docker engine was unavailable. CI is configured to exercise PostgreSQL but its result must be checked on GitHub.

If downloaded Chromium cannot launch on Windows, run browser tests with `$env:PLAYWRIGHT_CHANNEL="msedge"` to use installed Edge.

## Upgrade an existing checkout

Stop the API, run npm ci in frontend, run .venv/Scripts/python -m alembic upgrade head in backend, then rebuild the frontend with npm run build and start npm run preview; restart the API too. With Docker, use docker compose up --build -d. Existing records are preserved.

## Try Phase 2

1. Create a mission with an available team/vehicle and future check-in/return times.
2. Record departure, then a radio check-in and a position.
3. Inspect the next deadline, last confirmed location and observation age.
4. Use Update escalation for a deliberate operator decision; new contact does not clear it automatically.
5. Complete the mission after confirming everyone returned, then check the personnel overview.

The seeded PB-01 team is already in the field. Edit the planned FM-002 mission to suitable times before departing with its PB-02 team.

## Try Phase 3

Use the built preview (not npm run dev). Click Save mission pack and wait for both App shell cached and Mission pack saved. Disconnect and reload; record check-ins or positions, then reload again to verify they remain pending. Reconnect and click Send pending reports. Only a matching server receipt marks a report acknowledged. See [the offline guide](docs/OFFLINE.md).
