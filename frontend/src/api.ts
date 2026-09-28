export type Mission = {
  id: string;
  code: string;
  name: string;
  station: string;
  destination: string;
  status: string;
  departure: string;
  expected_check_in: string;
  expected_return: string;
};
export type Person = {
  id: string;
  name: string;
  role: string;
  station: string;
};
export type Vehicle = { id: string; code: string; kind: string };
export type MissionDetail = Mission & {
  personnel: Person[];
  vehicle: Vehicle;
  last_position: {
    latitude: number;
    longitude: number;
    observed_at: string;
    source: string;
  } | null;
  check_ins: {
    id: string;
    note: string;
    observed_at: string;
    source: string;
  }[];
};
export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch("/api/" + path, { signal });
  if (!response.ok)
    throw new Error(
      "Unable to load data (" +
        response.status +
        "). Check that the API is running.",
    );
  return response.json() as Promise<T>;
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
