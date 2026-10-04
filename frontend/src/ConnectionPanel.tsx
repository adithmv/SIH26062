import { useEffect, useRef, useState } from "react";

export type ConnectionState = "Not connected" | "Connecting" | "Checking" | "Reachable" | "Unreachable";
type Settings = { address: string; interval: number };
type Result = { address: string; reachable: boolean; message: string; checked_at: string; response_ms: number | null; version: string | null };
const storageKey = "pem-connection-settings";
function saved(): Settings {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (value && typeof value.address === "string" && [0, 15, 30, 60].includes(value.interval)) return value;
  } catch { /* Storage may be unavailable; manual connection still works. */ }
  return { address: "", interval: 30 };
}

export default function ConnectionPanel({ onStatus }: { onStatus: (status: ConnectionState) => void }) {
  const [draft, setDraft] = useState<Settings>(saved);
  const [active, setActive] = useState<Settings | null>(null);
  const [status, setStatus] = useState<ConnectionState>("Not connected");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [storageWarning, setStorageWarning] = useState("");
  const [check, setCheck] = useState(0);
  const generation = useRef(0);
  useEffect(() => { onStatus(status); }, [status, onStatus]);
  useEffect(() => {
    if (!active) return;
    const current = ++generation.current;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let attempt = 0;
    let cancelled = false;
    async function probe() {
      setStatus(attempt++ ? "Checking" : "Connecting"); setError("");
      const timeout = setTimeout(() => controller.abort(), 12000);
      try {
        const response = await fetch("/api/connection/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ address: active!.address }), signal: controller.signal, cache: "no-store" });
        const data = await response.json();
        if (cancelled || current !== generation.current) return;
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Connection check failed.");
        setResult(data); setStatus(data.reachable ? "Reachable" : "Unreachable");
      } catch (e) {
        if (cancelled || current !== generation.current) return;
        setResult(null);
        setStatus("Unreachable");
        setError(controller.signal.aborted ? "Check timed out. Use Check now to retry." : e instanceof TypeError ? "Cannot reach this device's backend to check the connection." : e instanceof Error ? e.message : "Connection check failed.");
      } finally {
        clearTimeout(timeout);
        if (!cancelled && current === generation.current && active!.interval > 0 && !controller.signal.aborted) timer = setTimeout(probe, active!.interval * 1000);
      }
    }
    void probe();
    return () => { cancelled = true; controller.abort(); clearTimeout(timer); };
  }, [active, check]);
  const modified = active && (draft.address.trim() !== active.address || draft.interval !== active.interval);
  const checking = status === "Connecting" || status === "Checking";
  function connect() {
    const settings = { ...draft, address: draft.address.trim().replace(/\/$/, "") };
    if (!settings.address) { setError("Enter the other device's backend address."); return; }
    try {
      const url = new URL(settings.address);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash || !["", "/"].includes(url.pathname)) throw new Error();
    } catch { setError("Use a backend address such as http://192.168.1.20:8000, without a path or password."); return; }
    try { localStorage.setItem(storageKey, JSON.stringify(settings)); setStorageWarning(""); }
    catch { setStorageWarning("Settings could not be saved in this browser. This connection can still be checked."); }
    setDraft(settings); setResult(null); setError(""); setActive(settings);
  }
  return <section className="connection-panel" aria-label="Device connection">
    <div className="connection-title"><h2>Connection</h2><strong role="status">{status}</strong></div>
    <p>Check the other device’s backend. These are real network checks; they do not send expedition files.</p>
    <form onSubmit={e => { e.preventDefault(); connect(); }}>
      <div className="connection-fields">
        <label>Other device address<input type="url" value={draft.address} onChange={e => setDraft({ ...draft, address: e.target.value })} placeholder="http://192.168.1.20:8000" maxLength={250} required /></label>
        <label>Automatic checks<select value={draft.interval} onChange={e => setDraft({ ...draft, interval: Number(e.target.value) })}><option value={0}>Manual only</option><option value={15}>Every 15 seconds</option><option value={30}>Every 30 seconds</option><option value={60}>Every 60 seconds</option></select></label>
      </div>
      <div className="actions"><button type="submit" disabled={checking && !modified}>{active ? "Apply and reconnect" : "Connect"}</button><button type="button" disabled={!active || checking} onClick={() => setCheck(v => v + 1)}>Check now</button><button type="button" disabled={!active} onClick={() => { ++generation.current; setActive(null); setStatus("Not connected"); setResult(null); setError(""); }}>Disconnect</button></div>
    </form>
    {modified && <p>Address or interval changed. Select Apply and reconnect to use these settings.</p>}
    {active && <p className="storage-path">Checking: {active.address}</p>}
    {result && <p>{result.message}<br />Last response: {new Date(result.checked_at).toLocaleString()}{result.response_ms !== null && ` · Response time: ${result.response_ms} ms`}{result.version && ` · Backend version: ${result.version}`}</p>}
    {error && <p role="alert" className="form-error">{error}</p>}
    {storageWarning && <p>{storageWarning}</p>}
    <small>Use localhost or a private network IP. “Reachable” is the last health-check result, not a permanent link or proof of identity. Editing settings does not change a running check until applied. Leaving Data Management or reloading stops checks; the address and interval stay saved.</small>
  </section>;
}
