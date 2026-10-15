# Frontend

For installation, follow the [main README](../README.md).

## Find the code

| File in `src/` | Purpose |
| --- | --- |
| `App.tsx` | Navigation and expedition overview |
| `DataManagement.tsx` | Files, data levels and prepared copies |
| `ConnectionPanel.tsx` | Saved connection settings and health checks |
| `BaseAccess.tsx` | Base sign-in and sessions |
| `BaseOperations.tsx` | Personnel, vehicles, cargo, inventory and alerts |
| `MissionForm.tsx`, `MissionWorkspace.tsx` | Plan and manage missions |
| `PositionMap.tsx`, `OnlineMap.tsx` | Recorded position display |
| `localStore.ts`, `OfflinePanel.tsx` | Offline reports and delivery |
| `api.ts`, `transport.ts` | Backend requests |

Styles are in `src/App.css` and `src/index.css`. Browser tests are in `tests/`.

## Check changes

From this folder:

```powershell
npm.cmd run build
npm.cmd run lint
```

Browser tests require an isolated test backend. GitHub runs them automatically on every push. Never run tests that create records against your real expedition database.
