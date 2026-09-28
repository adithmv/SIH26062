import { LinkDeferred, linkSettings } from "./connectivity";
import Dexie from "dexie";
import type { Table } from "dexie";
import type { Mission, MissionDetail, Person, Vehicle } from "./api";
import { ApiError, network } from "./transport";

type Snapshot = { key: string; value: unknown; savedAt: string };
export type ReportKind = "check-ins" | "positions";
export type ReportBody = {
  version: number;
  observed_at: string;
  source: string;
  note?: string;
  latitude?: number;
  longitude?: number;
  client_event_id?: string;
};
export type LocalReport = {
  id: string;
  missionId: string;
  missionCode: string;
  kind: ReportKind;
  body: ReportBody;
  createdAt: string;
};
export type Delivery = LocalReport & {
  state: "pending" | "sending" | "acknowledged" | "failed";
  error?: string;
  acknowledgedAt?: string;
  attempts?: number;
  retryAt?: number;
  conflict?: boolean;
  resolution?: string;
};
type Setting = { key: string; value: string };

class LocalDatabase extends Dexie {
  snapshots!: Table<Snapshot, string>;
  reports!: Table<LocalReport, string>;
  outbox!: Table<Delivery, string>;
  settings!: Table<Setting, string>;
  constructor() {
    super("polaris-local-v1");
    this.version(1).stores({
      snapshots: "key",
      reports: "id,missionId,createdAt",
      outbox: "id,missionId,state,createdAt",
      settings: "key",
    });
  }
}
export const db = new LocalDatabase();
export const STORE_ERROR =
  "Local storage is unavailable or full. Offline saving cannot be confirmed; keep a separate copy of unsent reports.";
export function announce() {
  window.dispatchEvent(new Event("polaris-local-change"));
}
export function storageProblem() {
  window.dispatchEvent(
    new CustomEvent("polaris-storage-error", { detail: STORE_ERROR }),
  );
}
export async function cacheValue(key: string, value: unknown) {
  try {
    await db.transaction("rw", db.snapshots, async () => {
      const previous = await db.snapshots.get(key);
      const version = (data: unknown) =>
        data &&
        typeof data === "object" &&
        "version" in data &&
        typeof data.version === "number"
          ? data.version
          : -1;
      if (version(previous?.value) > version(value)) return;
      await db.snapshots.put({ key, value, savedAt: new Date().toISOString() });
    });
  } catch {
    storageProblem();
  }
}
export async function cachedValue<T>(key: string): Promise<T | undefined> {
  const snapshot = await db.snapshots.get(key);
  const value = snapshot?.value;
  if (
    value &&
    typeof value === "object" &&
    "last_position" in value &&
    value.last_position &&
    "check_in_interval_minutes" in value
  ) {
    const mission = value as MissionDetail;
    const age = Math.max(
      0,
      Math.floor(
        (Date.now() - new Date(mission.last_position!.observed_at).getTime()) /
          60000,
      ),
    );
    return {
      ...mission,
      position_age_minutes: age,
      position_stale: age >= mission.check_in_interval_minutes,
    } as T;
  }
  return value as T | undefined;
}
export async function prepareOffline() {
  const [missions, people, vehicles] = await Promise.all([
    network<Mission[]>("missions"),
    network<Person[]>("personnel"),
    network<Vehicle[]>("vehicles"),
  ]);
  const details = await Promise.all(
    missions.map((m) => network<MissionDetail>("missions/" + m.id)),
  );
  const savedAt = new Date().toISOString();
  try {
    await db.transaction("rw", db.snapshots, db.settings, async () => {
      await db.snapshots.bulkPut([
        { key: "missions", value: missions, savedAt },
        { key: "personnel", value: people, savedAt },
        { key: "vehicles", value: vehicles, savedAt },
        ...details.map((value) => ({
          key: "missions/" + value.id,
          value,
          savedAt,
        })),
      ]);
      await db.settings.put({ key: "preparedAt", value: savedAt });
    });
  } catch {
    storageProblem();
    throw new Error(STORE_ERROR);
  }
  announce();
  return savedAt;
}
export async function saveReport(
  mission: MissionDetail,
  kind: ReportKind,
  body: ReportBody,
): Promise<MissionDetail> {
  const time = new Date(body.observed_at).getTime();
  if (mission.status !== "in_field")
    throw new Error("Reports require an in-field mission.");
  if (
    !Number.isFinite(time) ||
    time > Date.now() ||
    time < new Date(mission.actual_departure ?? mission.departure).getTime()
  )
    throw new Error("Observation time must be between departure and now.");
  if (kind === "check-ins" && (!body.note?.trim() || body.note.length > 500))
    throw new Error("Enter a check-in note of 1–500 characters.");
  if (
    kind === "positions" &&
    (!Number.isFinite(body.latitude) ||
      !Number.isFinite(body.longitude) ||
      Math.abs(body.latitude!) > 90 ||
      Math.abs(body.longitude!) > 180)
  )
    throw new Error("Enter valid latitude and longitude.");
  const id = crypto.randomUUID();
  const record: LocalReport = {
    id,
    missionId: mission.id,
    missionCode: mission.code,
    kind,
    body: { ...body, client_event_id: id },
    createdAt: new Date().toISOString(),
  };
  try {
    // The observation and its delivery entry succeed together or neither is saved.
    await db.transaction("rw", db.reports, db.outbox, async () => {
      await db.reports.add(record);
      await db.outbox.add({ ...record, state: "pending" });
    });
  } catch {
    storageProblem();
    throw new Error(STORE_ERROR);
  }
  announce();
  if (navigator.onLine) {
    try {
      await sendPending();
    } catch {
      window.dispatchEvent(
        new CustomEvent("polaris-storage-error", {
          detail:
            "Report saved locally, but delivery could not be confirmed. Check delivery history before retrying.",
        }),
      );
    }
  }
  return (
    (await cachedValue<MissionDetail>("missions/" + mission.id).catch(
      () => undefined,
    )) ?? mission
  );
}
export async function sendPending(retryId?: string, automatic = false) {
  if (linkSettings().profile === "offline" || !navigator.onLine) return;
  if (!navigator.locks)
    throw new Error(
      "This browser cannot safely coordinate delivery across tabs. Reports remain saved locally.",
    );
  await navigator.locks.request(
    "polaris-report-delivery",
    { ifAvailable: true },
    async (lock) => {
      if (!lock) return;
      if (retryId)
        await db.outbox.update(retryId, {
          state: "pending",
          error: undefined,
          attempts: 0,
          retryAt: 0,
        });
      const records = await db.outbox.orderBy("createdAt").toArray();
      // Safety check-ins precede location reports; timestamps break ties deterministically.
      records.sort(
        (a, b) =>
          (a.kind === "check-ins" ? 1 : 2) - (b.kind === "check-ins" ? 1 : 2) ||
          a.createdAt.localeCompare(b.createdAt) ||
          a.id.localeCompare(b.id),
      );
      const blocked = new Set(
        records.filter((r) => r.state === "failed").map((r) => r.missionId),
      );
      for (const entry of records) {
        if (
          entry.state === "acknowledged" ||
          entry.state === "failed" ||
          blocked.has(entry.missionId) ||
          (automatic &&
            ((entry.retryAt ?? 0) > Date.now() || (entry.attempts ?? 0) >= 5))
        )
          continue;
        // Read again: preceding acknowledgements may have advanced the version for this local sequence.
        const current = await db.outbox.get(entry.id);
        if (!current || current.state === "acknowledged") continue;
        await db.outbox.update(entry.id, {
          state: "sending",
          error: undefined,
        });
        announce();
        try {
          const result = await network<MissionDetail>(
            "missions/" + current.missionId + "/" + current.kind,
            "POST",
            current.body,
          );
          if (result.acknowledged_event_id !== current.id)
            throw new Error("Missing matching server receipt.");
          await db.transaction("rw", db.outbox, db.snapshots, async () => {
            await db.outbox.update(entry.id, {
              state: "acknowledged",
              acknowledgedAt: new Date().toISOString(),
              error: undefined,
            });
            await db.snapshots.put({
              key: "missions/" + result.id,
              value: result,
              savedAt: new Date().toISOString(),
            });
            // Only advance versions caused by our own just-acknowledged write; never resolve an external conflict silently.
            if (result.version === current.body.version + 1) {
              const waiting = await db.outbox
                .where("missionId")
                .equals(result.id)
                .toArray();
              for (const next of waiting)
                if (
                  next.state === "pending" &&
                  next.body.version === current.body.version
                ) {
                  await db.outbox.update(next.id, {
                    body: { ...next.body, version: result.version },
                  });
                }
            }
          });
        } catch (error) {
          const rejection =
            error instanceof ApiError &&
            error.status < 500 &&
            error.status !== 429;
          const deferred = error instanceof LinkDeferred;
          const attempts = (current.attempts ?? 0) + (deferred ? 0 : 1);
          await db.outbox.update(entry.id, {
            state: rejection ? "failed" : "pending",
            attempts,
            retryAt:
              Date.now() +
              (deferred ? 5000 : Math.min(60000, 2000 * 2 ** attempts)),
            conflict: error instanceof ApiError && error.status === 409,
            error: rejection
              ? error.message
              : deferred
                ? error.message
                : attempts >= 5
                  ? "Automatic retries paused after five attempts. Review connectivity, then send pending reports to retry."
                  : "No server acknowledgement received. Saved locally; automatic retry scheduled.",
          });
          blocked.add(entry.missionId);
          if (!rejection) break;
        } finally {
          announce();
        }
      }
    },
  );
}

export async function reviewConflict(id: string): Promise<MissionDetail> {
  const entry = await db.outbox.get(id);
  if (!entry?.conflict)
    throw new Error("This report has no version conflict to review.");
  return network<MissionDetail>("missions/" + entry.missionId);
}
export async function resolveConflict(id: string, reviewedVersion: number) {
  await navigator.locks.request("polaris-report-delivery", async () => {
    const entry = await db.outbox.get(id);
    if (!entry?.conflict || entry.state !== "failed")
      throw new Error("Report state changed; review it again.");
    await db.outbox.update(id, {
      body: { ...entry.body, version: reviewedVersion },
      state: "pending",
      attempts: 0,
      retryAt: 0,
      conflict: false,
      error: undefined,
      resolution:
        "Operator reviewed server version " +
        reviewedVersion +
        " and requested append. Original observation retained in reports.",
    });
  });
  await sendPending();
}
