# Phase 2 API and operational rules

Base path: /api. This prototype is unauthenticated and intended for local fictional demonstrations. Interactive schemas are at /docs. Offline writes, synchronization and emergency dispatch are not implemented.

## Endpoints

| Method | Path (after /api) | Purpose |
| --- | --- | --- |
| GET | /health | Database connectivity and version |
| GET | /missions | Plans plus calculated contact/return status |
| GET | /missions/{id} | Team, vehicle, position, age and check-ins |
| POST | /missions | Create a planned mission (201) |
| PUT | /missions/{id} | Replace editable mission plan |
| POST | /missions/{id}/depart | Record actual departure |
| POST | /missions/{id}/check-ins | Append check-in (201) |
| POST | /missions/{id}/positions | Append position (201) |
| POST | /missions/{id}/escalation | Operator escalation, emergency or clearance |
| POST | /missions/{id}/complete | Confirm team return |
| GET | /personnel | People and actual active mission |
| GET | /vehicles | Registered vehicles |
| GET | /events | Latest 100 audit events by receipt |

Missing IDs return 404, invalid inputs 422, and version/resource/code conflicts 409. Errors use the detail field. Collections may be empty; absent positions/contact times are null.

## Mission plan

Creation requires code, name, destination, station (return station), vehicle_id, personnel_ids, departure, expected_check_in and expected_return. Optional check_in_interval_minutes defaults to 60 (range 1–1440); overdue_grace_minutes defaults to 15 (range 0–240). PUT requires the same plan fields plus the current integer version.

All IDs are UUIDs. Teams cannot be empty or contain duplicates. First check-in must fall between departure and return, and return must follow departure. Times must include a timezone offset; they are normalized to UTC.

Overlapping planned/in-field missions cannot share a person or vehicle. Departure also rejects resources still in the field even after their expected return. PostgreSQL resource locks serialize competing reservations. SQLite is a single-machine demonstration adapter; multi-client concurrency requires PostgreSQL validation.

Lifecycle: planned → in_field → completed. Departure requires future check-in and return deadlines and records actual_departure using server UTC. Active team, vehicle and planned departure are immutable; other plan fields remain editable. Completed missions are read-only.

## Contact and return status

Evaluated at read time using server UTC. The interface polls every 30 seconds and displays evaluated_at.

- next_check_in = max(first expected check-in, latest check-in observation + interval), capped at expected return.
- Before deadline: normal.
- At deadline: check_in_due.
- At deadline + grace: contact_overdue; zero grace moves directly to overdue.
- At expected return: return_overdue becomes true until completion.
- Position reports update last contact/location but do not satisfy an explicit scheduled check-in.
- Delayed observations remain in history without moving the latest location or check-in deadline backward.
- Operator escalation/emergency overrides the headline status; underlying contact and return flags remain visible.
- New contact never silently clears an operator decision.
- Planned and completed missions are not automatically overdue.

These are configurable prototype rules, not approved expedition safety procedures.

## Observations

Check-ins accept version, observed_at, source, note. Positions accept version, observed_at, source, latitude and longitude. Sources: manual, radio, gnss, simulated_gnss, simulated_radio.

Observation time cannot be in the future or before actual departure (planned departure for the historic seeded in-field mission). The server assigns a separate received_at timestamp. Coordinates must be finite, latitude between -90 and 90, longitude between -180 and 180.

The latest position is selected by observation time, not receipt time. Detail includes position_age_minutes and position_stale; age reaching the configured check-in interval is stale. Missing positions are unknown/stale.

MapLibre's raster basemap requires internet and WebGL. Coordinates, source and times remain available without imagery. Mercator cannot accurately display the poles beyond approximately 85 degrees latitude. No route is inferred.

## Operator decisions and return

Escalation accepts version, level (none/escalation/emergency) and reason. Clearing also requires a reason. This only records an operator decision; it does not dispatch responders or transmit an SOS.

Completion accepts version and note. The interface requires confirmation that all personnel returned. Completion records the server time, clears active escalation, updates personnel to the return station and releases active resource accountability. Assignment, check-in, position and event history remains.

## Concurrency and audit

Each existing-mission mutation requires its current version. An atomic conditional update increments it. Stale submissions return 409 without partial changes. Refresh and reopen a form after conflict; background polling does not silently replace the version captured by an open form.

Mutation and audit event commit together. Events use stable UUIDs, device_id = server:<mission UUID>, and sequence = mission version. Seeded events retain their IDs. This is an audit foundation, not yet an offline sync protocol or tamper-proof ledger.

## Upgrade

Run alembic upgrade head from backend before starting the API. Migration 911a743ebba4 adds policy, escalation, actual departure and completion fields with defaults that preserve existing rows. Run alembic check to compare model and migration state.
