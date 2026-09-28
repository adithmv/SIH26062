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
  const response = await fetch("/api/" + path, {
    method,
    signal,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail
              .map(
                (e: { msg: string; loc: string[] }) =>
                  e.loc.slice(1).join(".") + ": " + e.msg,
              )
              .join("; ")
          : "Check that the API is running.";
    throw new Error(
      (method === "GET" ? "Unable to load data. " : "Not saved. ") + detail,
    );
  }
  return response.json() as Promise<T>;
}
export function get<T>(path: string, signal?: AbortSignal) {
  return request<T>(path, "GET", undefined, signal);
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
