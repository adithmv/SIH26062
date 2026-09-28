# Development roadmap

## Objective

Demonstrate that an expedition can keep recording operational events locally, prioritize transmission when bandwidth is scarce, and reconcile its state when connectivity returns.

Phases are ordered by dependency. Complete the prototype through Phase 6 before treating Phase 7 as a production deployment effort.

## Phase 0 — Scope and repository

Status: complete; initial documentation committed and pushed.

Deliverables:
- Repository, project overview and this roadmap.
- Agreed prototype boundary and planned technology stack.
- Explicit distinction between proposed features, simulated infrastructure and verified operational evidence.

Completion: initial documentation committed and pushed to GitHub.

## Phase 1 — Application foundation

Status: implemented; see README for setup and verification.

Deliverables:
- Frontend and backend scaffolds, PostgreSQL migrations and local Docker Compose configuration.
- Environment example without secrets, reproducible setup instructions and basic CI checks.
- Application navigation and deterministic fictional demonstration data.
- Initial personnel, mission, assignment, vehicle, position, check-in and event models.
- UTC timestamps, stable event identifiers and documented API contracts.

Completion: a fresh checkout can start the application, reach the API and load seeded missions using documented steps.

## Phase 2 — Personnel and mission accountability

Status: implemented and locally verified; PostgreSQL execution remains a CI/environment check.

Deliverables:
- Create a mission with personnel, vehicle, destination, departure, expected check-in and expected return.
- Record check-ins and positions with source, observed time and received time.
- Personnel overview, mission detail and map with last confirmed location and update age.
- Configurable check-in due and contact overdue rules, plus explicit operator escalation.
- Mission completion and personnel return workflow.

Completion: a seeded team can depart, check in, become overdue and return; stale positions remain visibly stale and missed contact does not automatically become an emergency.

## Phase 3 — Local-first operation

Status: implemented and locally verified for saved missions, offline check-ins/positions and explicit foreground delivery. Plans/lifecycle changes remain online-only.

Deliverables:
- Cached application shell and bounded local demo map assets.
- IndexedDB storage for mission data and an outgoing event queue.
- Atomic local writes for operational updates and their outgoing events.
- Visible pending, sending, acknowledged and failed delivery states.
- Persistence across reloads and clear handling of storage failures.

Completion: after initial setup, disconnect and reload; mission records remain available and new check-ins survive another reload without a server connection.

## Phase 4 — Connectivity-aware synchronization

Deliverables:
- Broadband, constrained and offline transport profiles.
- Reachability checks and a simulator that enforces latency, bandwidth budgets and request failures.
- Event priorities: SOS, personnel safety/location, critical inventory, routine updates and large attachments.
- Byte-budget-aware scheduling, bounded retries with backoff and separate attachment transfer.
- Server acknowledgements, idempotent event ingestion and reconnect synchronization.
- Version-aware conflict handling; append-only check-ins and positions, explicit resolution for incompatible mission edits.
- Separate event occurrence and receipt times so late events do not overwrite newer confirmed state.

Completion: constrained mode transmits eligible safety events before routine data; offline mode delivers nothing; reconnect drains the queue without duplicate effects or silent loss of conflicting changes.

## Phase 5 — Operational relationships

Deliverables:
- Link cargo and equipment to missions and vehicles.
- Basic cargo movement, equipment condition and stock-change records.
- Mission impact view showing affected personnel, vehicle, cargo and assets.
- Put related operational changes through the same local queue and priority policy.

Completion: selecting an overdue mission reveals its associated people and assets; inventory changes made offline synchronize correctly.

## Phase 6 — Integrated prototype and demonstration

Deliverables:
- Focused automated tests for priority ordering, duplicate delivery, conflicting edits, overdue rules and recovery.
- End-to-end tests covering offline reload, constrained delivery and reconnection.
- Repeatable demo controls with clearly labeled simulated locations and communication profiles.
- Visible queue depth, acknowledged events, delivery latency and transferred bytes.
- Demo guide and documented limitations, including browser background execution and storage constraints.

Completion scenario:
1. A team leaves a station with assigned vehicle and equipment.
2. Position updates arrive over the broadband profile.
3. Broadband fails and the constrained profile becomes available.
4. Photos wait while eligible personnel and safety updates transmit.
5. A missed check-in produces contact overdue status.
6. All communication is disabled; outgoing updates remain visibly pending.
7. Connectivity returns and queued events reconcile correctly.

## Phase 7 — Production readiness and field validation

This is a separate release gate; a successful simulated demonstration does not establish operational readiness.

Deliverables:
- Validate workflows and escalation policies with domain operators.
- Integrate and test actual GNSS sources and supported communication gateways.
- Add authenticated users, server-enforced station/mission authorization, secure provisioning and device revocation before exposing real data.
- Establish audit retention, encryption, backups, restore drills, monitoring and deployment procedures.
- Test multiple devices, long outages, clock skew, storage exhaustion and recovery at expected scale.
- Evaluate a native mobile or station gateway component for sustained background operation.
- Complete security review, field trials, operational training and acceptance criteria with stakeholders.

Completion: authorized stakeholders accept measured reliability and security results, supported hardware behavior and documented operational fallback procedures.

## Immediate next task

Start Phase 4: implement connectivity profiles, priority scheduling, bandwidth budgets, automatic delivery and explicit conflict resolution.
