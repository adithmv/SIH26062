import { lazy, Suspense, useState } from "react";
import type { FormEvent } from "react";
import { request, statusLabel, toISO, utc } from "./api";
import type { MissionDetail } from "./api";
const PositionMap = lazy(() => import("./PositionMap"));
type Action = "check-ins" | "positions" | "escalation" | "complete";

function ActionForm({
  mission,
  action,
  onSaved,
  onCancel,
}: {
  mission: MissionDetail;
  action: Action;
  onSaved: (m: MissionDetail) => void;
  onCancel: () => void;
}) {
  // Keep the version captured when this form opens; background refresh must not silently resolve a conflicting edit.
  const [version] = useState(mission.version);
  const [observed, setObserved] = useState(
    new Date().toISOString().slice(0, 23),
  );
  const [source, setSource] = useState("radio");
  const [note, setNote] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [level, setLevel] = useState("escalation");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const titles = {
    "check-ins": "Record check-in",
    positions: "Record position",
    escalation: "Update escalation",
    complete: "Confirm team return",
  };
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body =
        action === "check-ins"
          ? { version, observed_at: toISO(observed), source, note }
          : action === "positions"
            ? {
                version,
                observed_at: toISO(observed),
                source,
                latitude: Number(latitude),
                longitude: Number(longitude),
              }
            : action === "escalation"
              ? { version, level, reason: note }
              : { version, note };
      onSaved(
        await request<MissionDetail>(
          "missions/" + mission.id + "/" + action,
          "POST",
          body,
        ),
      );
      onCancel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="action-form" onSubmit={submit}>
      <h3>{titles[action]}</h3>
      <fieldset disabled={busy} className="form-fields">
        {(action === "positions" || action === "check-ins") && (
          <div className="form-grid">
            <label>
              Observed at (UTC)
              <input
                type="datetime-local"
                step="0.001"
                required
                value={observed}
                onChange={(e) => setObserved(e.target.value)}
              />
            </label>
            <label>
              Source
              <select
                aria-label="Source"
                value={source}
                onChange={(e) => setSource(e.target.value)}
              >
                <option value="radio">Radio report</option>
                <option value="manual">Manual observation</option>
                <option value="gnss">GNSS device</option>
                <option value="simulated_gnss">Simulated GNSS</option>
                <option value="simulated_radio">Simulated radio</option>
              </select>
            </label>
          </div>
        )}
        {action === "positions" ? (
          <div className="form-grid">
            <label>
              Latitude
              <input
                type="number"
                step="any"
                required
                min={-90}
                max={90}
                value={latitude}
                onChange={(e) => setLatitude(e.target.value)}
              />
            </label>
            <label>
              Longitude
              <input
                type="number"
                step="any"
                required
                min={-180}
                max={180}
                value={longitude}
                onChange={(e) => setLongitude(e.target.value)}
              />
            </label>
          </div>
        ) : (
          <>
            {action === "escalation" && (
              <label>
                Escalation level
                <select
                  aria-label="Escalation level"
                  value={level}
                  onChange={(e) => setLevel(e.target.value)}
                >
                  <option value="escalation">Escalation</option>
                  <option value="emergency">Emergency</option>
                  <option value="none">Clear manual escalation</option>
                </select>
              </label>
            )}
            <label>
              {action === "check-ins"
                ? "Check-in note"
                : action === "complete"
                  ? "Return note"
                  : "Reason"}
              <textarea
                required
                minLength={action === "check-ins" ? 1 : 3}
                maxLength={500}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </label>
          </>
        )}
        {action === "complete" && (
          <label className="check-label">
            <input
              type="checkbox"
              required
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
            />
            I confirm all assigned personnel have returned to {mission.station}.
          </label>
        )}
        {action === "escalation" && (
          <p className="muted">
            This records an operator decision. It does not dispatch responders
            or transmit an SOS.
          </p>
        )}
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="actions">
          <button type="submit" className="primary">
            {busy ? "Saving…" : "Save record"}
          </button>
          <button type="button" onClick={onCancel}>
            Cancel
          </button>
        </div>
      </fieldset>
    </form>
  );
}

export default function MissionWorkspace({
  mission,
  onSaved,
  onEdit,
  onBack,
}: {
  mission: MissionDetail;
  onSaved: (m: MissionDetail) => void;
  onEdit: () => void;
  onBack: () => void;
}) {
  const [action, setAction] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function depart() {
    setBusy(true);
    setError("");
    try {
      onSaved(
        await request<MissionDetail>(
          "missions/" + mission.id + "/depart",
          "POST",
          { version: mission.version },
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not depart.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <button className="back" onClick={onBack}>
        ← Back to missions
      </button>
      <div className="section-heading">
        <div>
          <p className="eyebrow">
            {mission.code} / {mission.station}
          </p>
          <h2>{mission.name}</h2>
        </div>
        <span className={"status " + mission.operational_status}>
          {statusLabel(mission.operational_status)}
        </span>
      </div>
      <p className="muted">
        Status evaluated {utc(mission.evaluated_at)} · refreshes every 30
        seconds
      </p>
      {mission.status === "in_field" &&
        (mission.contact_status !== "normal" || mission.return_overdue) && (
          <div className="attention" role="status">
            {mission.contact_status !== "normal" && (
              <p>
                Contact: {statusLabel(mission.contact_status)}. Check-in
                expected {utc(mission.next_check_in)}.
              </p>
            )}
            {mission.return_overdue && (
              <p>Expected return has passed: {utc(mission.expected_return)}.</p>
            )}
            <small>
              Overdue contact does not establish that a person is missing.
              Follow your team's escalation procedure.
            </small>
          </div>
        )}
      {mission.escalation_reason && (
        <p className="muted">
          Latest operator decision: {mission.escalation_reason}
        </p>
      )}
      {!action && mission.status !== "completed" && (
        <div className="actions">
          <button onClick={onEdit}>Edit plan</button>
          {mission.status === "planned" ? (
            <button className="primary" disabled={busy} onClick={depart}>
              {busy ? "Recording…" : "Record departure"}
            </button>
          ) : (
            <>
              <button onClick={() => setAction("check-ins")}>
                Record check-in
              </button>
              <button onClick={() => setAction("positions")}>
                Record position
              </button>
              <button onClick={() => setAction("escalation")}>
                Update escalation
              </button>
              <button onClick={() => setAction("complete")}>
                Complete mission
              </button>
            </>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {action && (
        <ActionForm
          key={action}
          mission={mission}
          action={action}
          onSaved={onSaved}
          onCancel={() => setAction(null)}
        />
      )}
      <div className="detail-grid">
        <div>
          <h3>Mission plan</h3>
          <p>Destination: {mission.destination}</p>
          <p>Planned departure: {utc(mission.departure)}</p>
          {mission.actual_departure && (
            <p>Actual departure: {utc(mission.actual_departure)}</p>
          )}
          <p>Next check-in: {utc(mission.next_check_in)}</p>
          <p>Expected return: {utc(mission.expected_return)}</p>
          <p>
            Check-in interval: {mission.check_in_interval_minutes} minutes ·
            Grace: {mission.overdue_grace_minutes} minutes
          </p>
          <p>Vehicle: {mission.vehicle.code}</p>
          {mission.completed_at && (
            <p>Team return confirmed: {utc(mission.completed_at)}</p>
          )}
          <h3>Last contact</h3>
          <p>
            {mission.last_contact_at
              ? utc(mission.last_contact_at)
              : "No field contact recorded"}
          </p>
        </div>
        <div>
          <h3>Assigned personnel</h3>
          {mission.personnel.map((p) => (
            <p key={p.id}>
              {p.name} <span className="muted">/ {p.role}</span>
            </p>
          ))}
          <h3>Last confirmed position</h3>
          {mission.last_position ? (
            <>
              <p>
                {mission.last_position.latitude.toFixed(4)}°,{" "}
                {mission.last_position.longitude.toFixed(4)}°
              </p>
              <p className="muted">
                {utc(mission.last_position.observed_at)}
                <br />
                {mission.last_position.source}
              </p>
              <span
                className={
                  "status " +
                  (mission.position_stale ? "contact_overdue" : "normal")
                }
              >
                {mission.position_age_minutes} minutes old
                {mission.position_stale ? " · stale observation" : ""}
              </span>
              <p className="muted">
                Received: {utc(mission.last_position.received_at)}
              </p>
            </>
          ) : (
            <p>No position recorded</p>
          )}
        </div>
      </div>
      {mission.last_position && (
        <Suspense fallback={<p>Loading map…</p>}>
          <PositionMap
            key={mission.last_position.id}
            position={mission.last_position}
          />
        </Suspense>
      )}
      <h3>Recorded check-ins</h3>
      {mission.check_ins.length ? (
        mission.check_ins.map((c) => (
          <article className="check-in" key={c.id}>
            <p>{c.note}</p>
            <small className="muted">
              Observed {utc(c.observed_at)} / {c.source}
              <br />
              Received {utc(c.received_at)}
            </small>
          </article>
        ))
      ) : (
        <p>No check-ins recorded</p>
      )}
    </section>
  );
}
