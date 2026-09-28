# Phase 3: local-first reporting

## Run the offline-capable build

The service worker is generated for a built application, not Vite's hot-reload development server. Docker now serves the built preview. For a local installation, run from frontend:

```powershell
npm ci
npm run build
npm run preview -- --port 5174 --strictPort
```

Keep the API running on port 8000 as before. Use localhost or HTTPS; service workers, UUID generation and cross-tab delivery locking require a secure browser context. Continue using the same hostname and port: browser storage is isolated by origin.

## Prepare and demonstrate

1. While connected, open the application and select **Save mission pack**. This downloads mission summaries, personnel, vehicles and every mission briefing into one local transaction.
2. Wait for **App shell cached** and **Mission pack saved**. These are separate readiness signals.
3. Disconnect the browser. Reload the page and open a saved in-field mission.
4. Record a check-in or position. It appears under **Reports saved on this device**, with **pending** delivery.
5. Reload again. Saved missions, local reports, delivery states and the bounded coordinate map remain available.
6. Reconnect and select **Send pending reports**. Matching server receipts change entries to **acknowledged**. Reconnection alone does not start background delivery in this phase.

Submitting a new report while connected also attempts delivery. Reports always commit locally before a transmission attempt.

## Storage and truthful status

IndexedDB (Dexie) database: polaris-local-v1, schema version 1.

| Store | Purpose |
| --- | --- |
| snapshots | Last downloaded API data, keyed by path, with savedAt |
| reports | Immutable locally captured observation with UUID, mission, source, occurrence time and original body |
| outbox | Delivery entry with the same UUID, state, payload version, error and acknowledgement time |
| settings | Last successful complete mission-pack save |

A local observation and its outgoing entry are written in a single transaction. If either write fails, both roll back and the form remains open. Storage failures are shown explicitly; a successful network read is not a promise that it was cached.

Delivery states:
- **pending:** saved locally, no matching receipt.
- **sending:** a delivery attempt is in progress.
- **acknowledged:** the server returned the same client_event_id after committing.
- **failed:** the server rejected the observation; the local copy and reason remain visible.

Interrupted sending entries can be retried. Web Locks prevent two tabs from sending the queue simultaneously. A network error or lost response returns an entry to pending; the server may already have accepted it, so retry uses its stable ID.

Server-confirmed history and locally pending reports are displayed separately. Pending reports do not clear server contact alerts or pretend to be received. Offline mission status retains its last server evaluation timestamp and a stale-data warning. Cached position age is recalculated using the device clock. Older-version read responses do not replace newer cached mission details.

## What works offline

- Read saved mission lists, briefings, personnel and vehicle records.
- Record check-ins and position observations for saved in-field missions.
- Reload the application and inspect delivery history.
- Display the bundled schematic coordinate grid covering 70.50–71.10° S, 11–12° E.

Mission creation/editing, departure, escalation and completion still require a server connection. The interface blocks plan/lifecycle changes while that mission has undelivered reports. Offline reports can still be captured when server status is stale; the server validates them at delivery.

The local map is a bounded coordinate grid, not terrain, a route or a navigation chart. Positions outside its extent retain their coordinates but are not drawn on the grid. The optional online map requires internet. No remote map-tile bulk download is performed.

## Minimal delivery protocol

Check-in and position endpoints accept optional client_event_id (UUID), and return acknowledged_event_id when that report is accepted. The audit event uses that ID. Replaying the same observation returns its receipt without another write, even if the mission version advanced or the mission completed. Reusing the ID for different contents/mission/type returns 409.

Queued observations are attempted in saved-time order. After this device's own acknowledgement advances the mission by exactly one version, waiting local observations based on the previous version advance together. External version conflicts are retained as failed reports; no automatic overwrite or version reset occurs. **Retry unchanged report** retries the same contents and cannot resolve an underlying version conflict.

This is a basic foreground delivery path. Priority scheduling, connection profiles, bandwidth budgets, automatic reconnection syncing and conflict-resolution workflows remain Phase 4.

## Limits and recovery

- Offline use requires initial download of both the app shell and mission data.
- **Keep data on device** requests persistent browser storage; the browser can decline.
- Browser data removal, private browsing cleanup or device loss can remove local records. There is no backup/export workflow yet.
- Do not clear site data to resolve a failed delivery. Keep the locally visible report until conflict resolution is implemented.
- An interrupted app update waits for existing tabs to close; it does not force a reload over an open form.
- Active transmission requires an open tab. This is not a background safety communication service.
- PostgreSQL integration is configured in CI; local checks use the SQLite demonstration adapter when Docker is unavailable.

## Verification

Browser tests serve a production build and exercise real service-worker caching and IndexedDB. They cover offline reload and map assets, durable reports, reconnection delivery, lost acknowledgements, atomic rollback on simulated quota failure and conflict retention. Backend tests cover receipt replay and mismatched IDs in addition to the mission workflows.


## Phase 4 connection simulator

Connection profiles persist for this browser origin. Broadband sends immediately. Constrained adds 800 ms latency and reserves at most 2,048 outgoing JSON payload bytes per 60-second window, coordinated across tabs. This is an application payload budget, not measured satellite bandwidth: responses, headers, health checks and online map downloads are outside the byte budget. Offline prevents API fetches. Failure simulation rejects requests until disabled; Check server connection performs a real health request through the selected profile.

While the app is open, automatic delivery checks every five seconds and on browser reconnection. Retry delays increase to a maximum of one minute; five unsuccessful attempts pause automatic retries. Manual Send pending reports retries retained pending entries. Budget deferrals do not consume retry attempts. Stable event IDs protect against duplicated effects after a lost receipt. Web Locks prevent simultaneous delivery from multiple tabs.

Check-ins precede positions, with creation time breaking ties. Original reports remain immutable in the reports store. A version rejection retains the report and blocks that mission's subsequent delivery. Review server conflict loads current server state; the operator can explicitly append the original observation using that reviewed version. Another concurrent change rejects it again. Completed missions cannot accept this resolution. Mission plan edits remain online with version checks.

Remaining Phase 4 scope: SOS and routine event producers, critical-inventory events (Phase 5), separate attachment storage/transfer, and scheduling all five priority classes. The current implementation only schedules existing check-in and position records; it does not claim those remaining event types are delivered.
