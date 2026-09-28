# SIH26062

A prototype expedition operations platform for polar missions, centered on a **Connectivity-Aware Mission Continuity Engine**.

The platform will connect personnel, field missions, vehicles, cargo and scientific assets while maintaining local operation through connectivity changes.

## Project status

Planning and initial repository setup. Application implementation has not started. The capabilities below are planned, not implemented.

## Prototype scope

- Personnel and field mission accountability: team assignments, destinations, last confirmed positions, check-ins and expected returns.
- Local-first recording with visible pending and acknowledged delivery states.
- Prioritized synchronization across broadband, constrained and disconnected conditions.
- Related vehicles, cargo and equipment for operational context.
- A reproducible demonstration of connection loss, overdue contact and recovery.

## Planned stack

| Component | Technology |
| --- | --- |
| Web application | React, TypeScript, Vite |
| Interface | Tailwind CSS, shadcn/ui |
| Offline application shell | PWA and service worker |
| Device storage | Dexie and IndexedDB |
| API and mission rules | Python and FastAPI |
| Central storage | PostgreSQL |
| Maps | MapLibre GL JS with locally available demo map assets |
| Synchronization | Custom client queue and server acknowledgement logic |
| Verification | Vitest, pytest, Playwright |
| Local demo environment | Docker Compose |

## Development phases

See [the development roadmap](docs/ROADMAP.md) for deliverables and completion criteria, from foundation through prototype demonstration and production hardening.

## Design boundaries

- Location means **last confirmed position**, with its source and timestamp; it is not a guarantee of current position.
- No communication link means no remote delivery, including SOS. Pending and delivered states must remain distinct.
- A missed check-in indicates overdue contact, not automatically a missing person or emergency.
- The prototype will simulate communication profiles; it will not claim actual satellite integration.
- Browser storage and background execution have limitations. This prototype is not a certified emergency communication system.
- Research claims about existing NCPOR systems require primary-source verification before publication.

## Getting started

There is no runnable application yet. Setup instructions will be added with the application scaffold in Phase 1.
