import { useEffect, useState } from "react";
import { request, utc } from "./api";
type Status = { checked_at: string; storage_root: string; free_bytes: number; storage_warning: boolean; stored_files: number; received_events: number; last_received_at: string | null; devices: { name: string; active: boolean }[] | null };
export default function BaseStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    request<Status>("base/status", "GET", undefined, controller.signal).then(value => { setStatus(value); setError(""); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [revision]);
  return <section className="panel"><h2>Base connection and storage</h2><p>This browser is connected to <strong>{window.location.origin}</strong>. Files below are stored on that base server. Field devices deliver records using their own registered credentials.</p><button onClick={() => setRevision(v => v + 1)}>Check base status</button>{error && <p role="alert">{error} Last displayed status may be stale.</p>}{status && <><p>Checked {utc(status.checked_at)} · {status.stored_files} files · {status.received_events} received events</p><p>Last event received: {status.last_received_at ? utc(status.last_received_at) : "None yet"}. This is a delivery timestamp, not proof that a field device is currently online.</p><p>Storage folder: <span className="storage-path">{status.storage_root}</span> · {(status.free_bytes / 1024 ** 3).toFixed(1)} GiB free</p>{status.storage_warning && <p role="alert">Storage is running low. Arrange space before accepting more files.</p>}{status.devices && <><h3>Registered field devices</h3>{status.devices.length ? <ul>{status.devices.map(d => <li key={d.name}>{d.name} — {d.active ? "Delivery access enabled" : "Access disabled"}</li>)}</ul> : <p>No field devices registered. Your administrator can register them from the server console.</p>}</>}</>}</section>;
}
