# Phase 1 API and data contracts

Base path: `/api`. All Phase 1 endpoints are read-only and unauthenticated for local fictional demonstration use. The frontend uses a same-origin development proxy.

## Endpoints

| Method | Path | Response |
| --- | --- | --- |
| GET | /api/health | Status and API version; 503 if database connectivity fails |
| GET | /api/missions | Mission array ordered by code |
| GET | /api/missions/{id} | Mission plus personnel, vehicle, last_position and check_ins |
| GET | /api/personnel | Personnel array ordered by name |
| GET | /api/vehicles | Vehicle array ordered by code |
| GET | /api/events | At most 100 events, newest occurrence first |

Unknown mission IDs return 404; malformed UUIDs return 422. Errors use FastAPI's `detail` field. An empty collection is `[]`; no recorded position is `null`. Health checks database connectivity, not migration completeness.

## Shared rules

- IDs are UUID strings. Demo seeds use deterministic UUIDv5 identifiers; future records default to UUIDv4.
- Timestamps serialize as ISO 8601 UTC with an explicit offset.
- `observed_at` / `occurred_at` identify the field observation; `received_at` identifies receipt by the server.
- Mission timestamps: `departure`, `expected_check_in`, `expected_return`.
- Newest confirmed position is selected by observation time, not arrival time.
- There are no write or sync endpoints yet. Event storage does not imply delivery acknowledgement or a working sync engine.

## Entities

| Entity | Fields and relationships |
| --- | --- |
| Personnel | id, name, role, station |
| Vehicle | id, unique code, kind |
| Mission | id, unique code, name, destination, station, status, vehicle_id, departure, expected_check_in, expected_return, version |
| Assignment | composite key (mission_id, personnel_id), both foreign keys |
| Position | id, mission_id, latitude [-90,90], longitude [-180,180], source, observed_at, received_at |
| CheckIn | id, mission_id, source, note, observed_at, received_at |
| Event | id, mission_id, device_id, sequence, kind, priority [0,4], occurred_at, received_at, payload |

Mission detail includes `personnel: Personnel[]`, `vehicle: Vehicle`, `last_position: Position | null`, and `check_ins: CheckIn[]`.

Mission return must follow departure; expected check-in cannot precede departure. Device ID and sequence are unique together. Events reference their mission; JSON payloads carry a schema_version for future evolution. Demo event payloads reference the associated check-in ID.

The initial fixture statuses are `planned` and `in_field`. Status transitions and conflict rules are intentionally deferred to their roadmap phases.

## Migration workflow

From backend, with the virtual environment active:

```text
alembic revision --autogenerate -m descriptive_change
alembic upgrade head
alembic check
```

Review generated migrations before applying them. Initial migrations explicitly define their tables; they do not import evolving application models. Production migration scheduling and deployment are outside Phase 1.
