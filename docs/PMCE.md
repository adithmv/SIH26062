# PMCE event contract

## Event envelope

POST `/api/pmce/outbox` on field or `/api/pmce/events` on central.

Required: `id` (new UUID), `device_id` (1-80 characters), `mission_id` (UUID), `kind`, `occurred_at` (ISO timestamp with timezone), `payload` (below). Use your own records; there are no seeded missions or resource IDs.

| Kind | Priority | Required payload fields |
| --- | --- | --- |
| `sos` | P0 | `message` |
| `check_in` | P1 | `source`, `note` |
| `position` | P1 | `source`, `latitude`, `longitude` |
| `critical_inventory` | P2 | `item_id`, `expected_version`, `delta`, `note` |
| `vehicle_status` | P2 | `vehicle_id`, `condition`, `note` |
| `asset_condition` | P2 | `asset_id`, `condition`, `note` |
| `inventory_update` | P3 | `item_id`, `expected_version`, `delta`, `note` |
| `cargo_movement` | P3 | `cargo_id`, `expected_version`, `status`, `location`, `note` |
| `mission_log` | P3 | `note` |
| `report` | P4 | `title`, `text` |

Sources: `manual`, `radio`, `gnss`. Conditions: `unknown`, `operational`, `maintenance`, `unserviceable`. Coordinates must be finite and geographically valid. Unknown fields are rejected. Priority is assigned by kind.

## Central rules

- New events require an existing in-field mission. Occurrence time must be between actual departure and server time.
- Receipt, audit and effects commit together. Invalid events produce no partial changes.
- Identical ID/content replays return the original receipt, including after completion. Different contents with the same ID return 409.
- Late observations remain in history without replacing newer positions/contact. Condition uses the latest observed time; equal timestamps preserve the accepted state.
- SOS creates an alert and raises escalation to emergency. Operator acknowledgement and resolution require current alert `version`, `operator` and `note`. Names are operator-entered attribution, not authenticated identities.
- Open alerts prevent mission completion or lowering escalation. Resolving an alert does not automatically clear escalation.
- Cargo follows `registered -> loaded -> in_transit -> delivered`; loaded/in-transit/delivered cargo can become `returned`. Movements require the current version and cannot predate the last movement.
- Stock uses nonzero integer deltas, a current version and a balance between zero and one billion. Critical stock requires `critical_inventory`; ordinary stock requires `inventory_update`.
- Stock, equipment and cargo must be linked to the mission. Supply links do not reserve/deduct quantity. Register/assign resources before departure.

## Conflict recovery

Temporary failures wait 5, 10, 20 and 40 seconds between attempts; five failures pause delivery. Manual retry resets failures while preserving contents and lifetime attempts. HTTP 4xx rejections block the event, except 408/429.

Read current central stock/cargo first. POST a replacement to `/api/pmce/outbox/{original_id}/resolve`, preserving all fields except a new `id` and a higher reviewed `payload.expected_version`. The blocked original remains `superseded`. A changed central version can reject the replacement again. Quantity/transition errors require resolving the underlying situation, not rewriting the observation.

## Transport and inspection

Plan/sync requires `mode`; optional `byte_budget` defaults to 2048, `limit` to 100, `compression` to false. Offline sends nothing; limited sends P0-P2 within the payload budget; broadband sends all priorities. Queue order is priority, queue time, event ID. Plans list only currently due, unblocked entries. Oversized events wait for a suitable budget/mode.

Outbox supports `offset`, `limit`, `pending_only`; central events support `offset`, `limit`. Entries show delivery state, error, retry time, attempts, supersession, byte counts and delivery duration. Status returns queue counts, priorities and transmission totals.

The first temporary failure ends a pass. Rejected events remain visible while later work proceeds. Only a matching receipt acknowledges delivery. Gzip is optional and used only when smaller. Requests are limited to 64 KiB including after decompression. Counters exclude HTTP overhead/responses. Connection profiles are explicitly selected, not measured.
