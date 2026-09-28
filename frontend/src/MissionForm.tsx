import { useState } from "react";
import type { FormEvent } from "react";
import { dateInput, request, toISO } from "./api";
import type { MissionDetail, Person, Vehicle } from "./api";

type Props = {
  initial?: MissionDetail;
  people: Person[];
  vehicles: Vehicle[];
  onSaved: (m: MissionDetail) => void;
  onCancel: () => void;
};
export default function MissionForm({
  initial,
  people,
  vehicles,
  onSaved,
  onCancel,
}: Props) {
  const [draft, setDraft] = useState(() => ({
    code: initial?.code ?? "",
    name: initial?.name ?? "",
    destination: initial?.destination ?? "",
    station: initial?.station ?? "Maitri",
    vehicle_id: initial?.vehicle_id ?? vehicles[0]?.id ?? "",
    personnel_ids: initial?.personnel.map((p) => p.id) ?? ([] as string[]),
    departure: dateInput(initial?.departure ?? new Date().toISOString()),
    expected_check_in: dateInput(
      initial?.expected_check_in ??
        new Date(Date.now() + 3600000).toISOString(),
    ),
    expected_return: dateInput(
      initial?.expected_return ?? new Date(Date.now() + 14400000).toISOString(),
    ),
    check_in_interval_minutes: initial?.check_in_interval_minutes ?? 60,
    overdue_grace_minutes: initial?.overdue_grace_minutes ?? 15,
    version: initial?.version,
  }));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const locked = initial?.status === "in_field";
  const field = (key: string, value: string | number) =>
    setDraft((d) => ({ ...d, [key]: value }));
  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const { version, ...values } = draft;
      const body = {
        ...values,
        departure: toISO(draft.departure),
        expected_check_in: toISO(draft.expected_check_in),
        expected_return: toISO(draft.expected_return),
        ...(initial ? { version } : {}),
      };
      // Preserve the exact timestamp while editing an active mission's immutable departure.
      if (locked && initial) body.departure = initial.departure;
      onSaved(
        await request<MissionDetail>(
          initial ? "missions/" + initial.id : "missions",
          initial ? "PUT" : "POST",
          body,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save mission.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>{initial ? "Edit mission plan" : "Create a field mission"}</h2>
      <p className="muted">
        Assign a team and vehicle, then set a check-in schedule. All times below
        are UTC.
      </p>
      <form onSubmit={submit}>
        <fieldset disabled={busy} className="form-fields">
          <div className="form-grid">
            <label>
              Mission code
              <input
                required
                maxLength={40}
                pattern="[A-Za-z0-9_-]+"
                value={draft.code}
                onChange={(e) => field("code", e.target.value)}
              />
            </label>
            <label>
              Mission name
              <input
                required
                maxLength={120}
                value={draft.name}
                onChange={(e) => field("name", e.target.value)}
              />
            </label>
            <label>
              Destination
              <input
                required
                maxLength={120}
                value={draft.destination}
                onChange={(e) => field("destination", e.target.value)}
              />
            </label>
            <label>
              Return station
              <input
                required
                maxLength={80}
                value={draft.station}
                onChange={(e) => field("station", e.target.value)}
              />
            </label>
            <label>
              Vehicle
              <select
                aria-label="Vehicle"
                required
                disabled={locked}
                value={draft.vehicle_id}
                onChange={(e) => field("vehicle_id", e.target.value)}
              >
                {vehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.code} — {v.kind}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Departure (UTC)
              <input
                required
                disabled={locked}
                type="datetime-local"
                value={draft.departure}
                onChange={(e) => field("departure", e.target.value)}
              />
            </label>
            <label>
              First check-in (UTC)
              <input
                required
                type="datetime-local"
                value={draft.expected_check_in}
                onChange={(e) => field("expected_check_in", e.target.value)}
              />
            </label>
            <label>
              Expected return (UTC)
              <input
                required
                type="datetime-local"
                value={draft.expected_return}
                onChange={(e) => field("expected_return", e.target.value)}
              />
            </label>
            <label>
              Check-in interval (minutes)
              <input
                required
                type="number"
                min={1}
                max={1440}
                value={draft.check_in_interval_minutes}
                onChange={(e) =>
                  field("check_in_interval_minutes", Number(e.target.value))
                }
              />
            </label>
            <label>
              Overdue grace (minutes)
              <input
                required
                type="number"
                min={0}
                max={240}
                value={draft.overdue_grace_minutes}
                onChange={(e) =>
                  field("overdue_grace_minutes", Number(e.target.value))
                }
              />
            </label>
          </div>
          <fieldset className="team-picker" disabled={locked}>
            <legend>Assigned personnel (select at least one)</legend>
            {people.map((p) => (
              <label className="check-label" key={p.id}>
                <input
                  type="checkbox"
                  checked={draft.personnel_ids.includes(p.id)}
                  onChange={(e) =>
                    setDraft((d) => ({
                      ...d,
                      personnel_ids: e.target.checked
                        ? [...d.personnel_ids, p.id]
                        : d.personnel_ids.filter((id) => id !== p.id),
                    }))
                  }
                />
                {p.name} <span className="muted">{p.role}</span>
              </label>
            ))}
          </fieldset>
          {locked && (
            <p className="muted">
              The team, vehicle and departure stay fixed while a mission is in
              the field.
            </p>
          )}
          {error && (
            <p role="alert" className="form-error">
              {error} If another operator changed this mission, cancel and
              reopen the form to use the latest version.
            </p>
          )}
          <div className="actions">
            <button
              className="primary"
              disabled={!draft.personnel_ids.length}
              type="submit"
            >
              {busy ? "Saving…" : "Save mission"}
            </button>
            <button type="button" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  );
}
