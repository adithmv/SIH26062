import { cacheValue, cachedValue } from "./localStore";
import { ApiError, network } from "./transport";
export type Mission = {
  id: string;
  code: string;
  name: string;
  station: string;
  destination: string;
  status: "planned" | "in_field" | "completed";
  vehicle_id: string;
  version: number;
  departure: string;
  expected_check_in: string;
  expected_return: string;
  check_in_interval_minutes: number;
  overdue_grace_minutes: number;
  escalation_level: string;
  escalation_reason: string | null;
  actual_departure: string | null;
  completed_at: string | null;
  operational_status: string;
  contact_status: string;
  return_overdue: boolean;
  evaluated_at: string;
  next_check_in: string;
  last_contact_at: string | null;
};
export type Person = {
  id: string;
  name: string;
  role: string;
  station: string;
  operational_status: string;
  active_mission_id: string | null;
  active_mission_code: string | null;
};
export type Vehicle = { id: string; code: string; kind: string };
export type Position = {
  id: string;
  latitude: number;
  longitude: number;
  source: string;
  observed_at: string;
  received_at: string;
};
export type MissionDetail = Mission & {
  acknowledged_event_id?: string | null;
  personnel: Person[];
  vehicle: Vehicle;
  last_position: Position | null;
  position_age_minutes: number | null;
  position_stale: boolean;
  check_ins: {
    id: string;
    note: string;
    source: string;
    observed_at: string;
    received_at: string;
  }[];
};
export async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const value = await network<T>(path, method, body, signal);
  if (method === "GET") await cacheValue(path, value);
  else if (value && typeof value === "object" && "id" in value)
    await cacheValue("missions/" + String(value.id), value);
  return value;
}
export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  try {
    const value = await request<T>(path, "GET", undefined, signal);
    window.dispatchEvent(
      new CustomEvent("polaris-read", { detail: { path, cached: false } }),
    );
    return value;
  } catch (error) {
    if (signal?.aborted || (error instanceof ApiError && error.status < 500))
      throw error;
    const cached = await cachedValue<T>(path).catch(() => undefined);
    if (cached !== undefined) {
      window.dispatchEvent(
        new CustomEvent("polaris-read", { detail: { path, cached: true } }),
      );
      return cached;
    }
    throw new Error(
      "Unable to load data. No saved copy is available on this device. Connect and save a mission pack first.",
    );
  }
}
export function utc(value: string) {
  return (
    new Intl.DateTimeFormat("en-GB", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "UTC",
    }).format(new Date(value)) + " UTC"
  );
}
export function dateInput(value: string) {
  return new Date(value).toISOString().slice(0, 16);
}
export function toISO(value: string) {
  return new Date(value + "Z").toISOString();
}
export function statusLabel(value: string) {
  return value === "normal" ? "In field · normal" : value.replaceAll("_", " ");
}
