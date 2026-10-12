import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { request, utc } from "./api";
import type { Mission } from "./api";
import { baseUser } from "./baseMode";

type Area = "personnel" | "vehicles" | "cargo" | "inventory" | "alerts";
type Row = { id: string; version: number; [key: string]: string | number | boolean | null };
const fields: Record<Area, [string, string, number][]> = {
  personnel: [["name", "Name", 120], ["role", "Role", 80], ["station", "Station", 80]],
  vehicles: [["code", "Vehicle code", 40], ["kind", "Vehicle type", 80]],
  cargo: [["code", "Cargo code", 40], ["description", "Description", 500], ["location", "Location", 120]],
  inventory: [["sku", "Item code", 40], ["name", "Item name", 120], ["station", "Station", 80], ["unit", "Unit (such as litres)", 30]],
  alerts: [],
};
const columns: Record<Area, [string, string][]> = {
  personnel: [["name", "Name"], ["role", "Role"], ["station", "Station"]],
  vehicles: [["code", "Code"], ["kind", "Type"], ["condition", "Condition"]],
  cargo: [["code", "Code"], ["description", "Description"], ["mission_id", "Mission"], ["location", "Location"], ["status", "Status"]],
  inventory: [["sku", "Code"], ["name", "Name"], ["station", "Station"], ["quantity", "Available"], ["unit", "Unit"]],
  alerts: [["message", "Alert"], ["mission_id", "Mission"], ["received_at", "Received at"], ["acknowledged_by", "Acknowledged by"], ["resolved_by", "Resolved by"]],
};

export function RegisterResource({ area, onSaved }: { area: "personnel" | "vehicles"; onSaved: () => void }) {
  return <CreateForm area={area} missions={[]} onSaved={onSaved} />;
}

function CreateForm({ area, missions, onSaved }: { area: Area; missions: Mission[]; onSaved: () => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  if (baseUser?.role === "viewer" || area === "alerts") return null;
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending.current) return;
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    pending.current = true; setBusy(true); setError("");
    try {
      await request(area, "POST", body);
      form.reset(); onSaved();
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save."); }
    finally { pending.current = false; setBusy(false); }
  }
  return <details className="panel"><summary>Add {area === "personnel" ? "person" : area === "vehicles" ? "vehicle" : area === "inventory" ? "stock item" : "cargo"}</summary><form onSubmit={save}><fieldset disabled={busy} className="form-grid">{fields[area].map(([key, label, max]) => <label key={key}>{label}<input name={key} required maxLength={max} /></label>)}{area === "cargo" && <label>Mission<select name="mission_id" required defaultValue=""><option value="" disabled>Select planned mission</option>{missions.filter(m => m.status === "planned").map(m => <option key={m.id} value={m.id}>{m.code} · {m.name}</option>)}</select></label>}<button type="submit">{busy ? "Saving…" : "Save"}</button></fieldset>{error && <p role="alert">{error}</p>}</form></details>;
}

export default function BaseOperations({ area, missions, revision }: { area: "cargo" | "inventory" | "alerts"; missions: Mission[]; revision: number }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [offset, setOffset] = useState(0);
  const [generation, setGeneration] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Row | null>(null);
  const [action, setAction] = useState("");
  const [note, setNote] = useState("");
  const [delta, setDelta] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const pending = useRef(false);
  const movement = useRef({ id: crypto.randomUUID(), occurred_at: new Date().toISOString() });
  const [actionError, setActionError] = useState("");
  const canEdit = baseUser?.role !== "viewer";
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => { if (!controller.signal.aborted) setLoading(true); });
    request<Row[]>(`${area}?limit=50&offset=${offset}`, "GET", undefined, controller.signal)
      .then(value => { setRows(value); setError(""); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [area, offset, revision, generation]);
  function open(row: Row, value: string) {
    setSelected({ ...row }); setAction(value); setNote(""); setDelta(""); setActionError("");
    movement.current = { id: crypto.randomUUID(), occurred_at: new Date().toISOString() };
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || pending.current) return;
    pending.current = true; setBusy(true); setActionError(""); setNotice("");
    try {
      if (area === "inventory") {
        await request("inventory/adjustments", "POST", { ...movement.current, item_id: selected.id, expected_version: selected.version, delta: Number(delta), note });
      } else {
        await request(`alerts/${selected.id}/${action}`, "POST", { version: selected.version, operator: baseUser?.username, note });
      }
      setSelected(null); setNotice("Saved at the base station."); setGeneration(v => v + 1);
    } catch (e) { setActionError(e instanceof Error ? e.message : "Could not save. Refresh before retrying."); }
    finally { pending.current = false; setBusy(false); }
  }
  return <section aria-label={`Base ${area}`}><p>{area === "alerts" ? "Alerts received from field devices. Acknowledge receipt, then record the outcome when resolved. This does not dispatch emergency services." : area === "inventory" ? "Stock stored at the station. Add an item, then record each increase or decrease with a reason." : "Cargo registered against planned missions. Updates received from field devices appear here."}</p><CreateForm area={area} missions={missions} onSaved={() => { setNotice("Record saved."); setGeneration(v => v + 1); }} />{error && <p role="alert">{error} Displayed records may be stale. <button onClick={() => setGeneration(v => v + 1)}>Retry</button></p>}{notice && <p role="status">{notice}</p>}{loading && <p role="status">Loading records…</p>}<div className="table-wrap"><table><thead><tr>{columns[area].map(([key, label]) => <th key={key}>{label}</th>)}{canEdit && area !== "cargo" && <th>Action</th>}</tr></thead><tbody>{rows.map(row => <tr key={row.id}>{columns[area].map(([key]) => <td key={key}>{key === "mission_id" ? missions.find(m => m.id === row[key])?.code ?? String(row[key]) : key === "received_at" && row[key] ? utc(String(row[key])) : String(row[key] ?? "—")}</td>)}{canEdit && area !== "cargo" && <td>{area === "inventory" ? <button disabled={busy || loading || !!error} onClick={() => open(row, "adjust")}>Adjust stock</button> : !row.resolved_at && <button disabled={busy || loading || !!error} onClick={() => open(row, row.acknowledged_at ? "resolve" : "acknowledge")}>{row.acknowledged_at ? "Resolve" : "Acknowledge"}</button>}</td>}</tr>)}</tbody></table></div>{!loading && !error && rows.length === 0 && <p>No {area} records on this page.</p>}<p><button disabled={offset === 0 || loading || busy} onClick={() => setOffset(v => Math.max(0, v - 50))}>Previous</button> Page {offset / 50 + 1} <button disabled={rows.length < 50 || loading || busy} onClick={() => setOffset(v => v + 50)}>Next</button></p>{selected && <form className="panel" onSubmit={submit}><h2>{area === "inventory" ? `Adjust ${selected.name}` : action === "resolve" ? "Resolve alert" : "Acknowledge alert"}</h2><fieldset disabled={busy}>{area === "inventory" && <label>Quantity change (negative for stock used)<input type="number" required step="1" min="-1000000000" max="1000000000" value={delta} onChange={e => setDelta(e.target.value)} /></label>}<label>Reason / action taken<textarea required maxLength={500} value={note} onChange={e => setNote(e.target.value)} /></label><button type="submit">{busy ? "Saving…" : "Confirm"}</button><button type="button" onClick={() => setSelected(null)}>Cancel</button></fieldset>{actionError && <p role="alert">{actionError}</p>}</form>}</section>;
}
