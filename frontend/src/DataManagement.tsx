import { useEffect, useState } from "react";

type Copy = { id: string; size: number; compressed: boolean; encrypted: boolean; storage_path: string };
type StoredFile = { id: string; name: string; size: number; importance: string; confidentiality: string; storage_path: string; status: string; copies: Copy[] };
type Listing = { storage_root: string; max_bytes: number; files: StoredFile[] };
const size = (bytes: number) => `${bytes.toLocaleString()} bytes`;
async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/api/files${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "Could not complete the file operation.");
  }
  return response;
}
const json = (body: unknown, method = "POST") => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export default function DataManagement({ revision }: { revision: number }) {
  const [listing, setListing] = useState<Listing | null>(null);
  const [selected, setSelected] = useState<StoredFile | null>(null);
  const [importance, setImportance] = useState("normal");
  const [confidentiality, setConfidentiality] = useState("normal");
  const [ready, setReady] = useState(false);
  const [compress, setCompress] = useState(true);
  const [encrypt, setEncrypt] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [unlock, setUnlock] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function refresh() {
    const data: Listing = await (await request("")).json();
    setListing(data);
    setSelected(current => current ? data.files.find(file => file.id === current.id) ?? null : null);
  }
  useEffect(() => {
    let active = true;
    request("").then(response => response.json()).then((data: Listing) => {
      if (!active) return;
      setListing(data);
      setSelected(current => current ? data.files.find(file => file.id === current.id) ?? null : null);
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [revision]);
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "File operation failed."); }
    finally { setBusy(false); }
  }
  function edit(file: StoredFile) {
    setSelected(file); setImportance(file.importance); setConfidentiality(file.confidentiality);
    setReady(false); setCompress(true); setEncrypt(false); setPassword(""); setConfirmation(""); setUnlock(""); setNotice(""); setError("");
  }
  async function upload(file?: File) {
    if (!file) return;
    await run(async () => {
      if (!listing) throw new Error("Wait for storage to load before uploading.");
      if (file.size > listing.max_bytes) throw new Error("Maximum file size is 20 MiB.");
      await request(`?name=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
      await refresh(); setNotice("File stored locally. Its location is shown below.");
    });
  }
  return <section className="data-management" aria-label="File storage">
    <p>Upload expedition files, see where they are stored, and prepare compressed or encrypted copies.</p>
    <div className="panel">
      <strong>Storage folder on this backend computer</strong>
      <p className="storage-path">{listing?.storage_root ?? "Loading storage location…"}</p>
      <p>Originals go in <b>originals</b>; prepared copies go in <b>prepared</b>. Up to 20 MiB per file. Nothing is sent to base from this page yet.</p>
      <label>Add a file <input type="file" disabled={busy || !listing} onChange={e => { void upload(e.target.files?.[0]); e.target.value = ""; }} /></label>
    </div>
    {error && <p role="alert" className="form-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">Working… Please keep this page open.</p>}
    {listing && listing.files.length === 0 && <p className="panel">No files stored yet. Add your first expedition file above.</p>}
    {!!listing?.files.length && <div className="table-wrap"><table><thead><tr><th>File</th><th>Data level</th><th>Storage location</th><th>Actions</th></tr></thead><tbody>
      {listing.files.map(file => <tr key={file.id}>
        <td><strong>{file.name}</strong><br />{size(file.size)}<br /><small>{file.status}</small></td>
        <td>{file.importance} / {file.confidentiality}<br /><small>Original: not encrypted</small></td>
        <td className="storage-path">{file.storage_path}</td>
        <td><button disabled={busy} onClick={() => edit(file)}>Edit data level</button><br /><a href={`/api/files/${file.id}/download`}>Download original</a></td>
      </tr>)}
    </tbody></table></div>}
    {selected && <section className="panel" aria-label="Edit data level">
      <div className="page-heading"><h2>Edit data level — {selected.name}</h2><button disabled={busy} onClick={() => { setSelected(null); setPassword(""); setConfirmation(""); setUnlock(""); }}>Close</button></div>
      <div className="file-split">
        <div><h3>1. Select the original</h3>
          <div className="file-drop" draggable={!busy} onDragStart={e => e.dataTransfer.setData("text/plain", selected.id)}>
            <strong>{selected.name}</strong><p>{size(selected.size)}</p><p className="storage-path">{selected.storage_path}</p>
            <p>Drag this file to the preparation area, or use the button.</p>
            <button disabled={busy} onClick={() => setReady(true)}>Use this file</button>
          </div>
          <p>The original stays unchanged and unencrypted. A confidential label alone does not protect its contents.</p>
        </div>
        <div><h3>2. Set level and prepare a copy</h3>
          <fieldset disabled={busy}>
            <label>Importance<select value={importance} onChange={e => setImportance(e.target.value)}><option value="normal">Normal</option><option value="important">Important</option><option value="critical">Critical</option></select></label>
            <label>Confidentiality<select value={confidentiality} onChange={e => setConfidentiality(e.target.value)}><option value="normal">Normal</option><option value="confidential">Confidential</option></select></label>
            <button onClick={() => void run(async () => { await request(`/${selected.id}`, json({ importance, confidentiality }, "PATCH")); await refresh(); setNotice("Data level saved. File contents are unchanged."); })}>Save data level</button>
            <div className="file-drop" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy && e.dataTransfer.getData("text/plain") === selected.id) setReady(true); }}>
              {ready ? `Selected: ${selected.name}` : "Preparation area — drop the original here or choose Use this file."}
            </div>
            <label className="file-check"><input type="checkbox" checked={compress} onChange={e => setCompress(e.target.checked)} /> Compress the copy</label>
            <p>Compression runs first. Some file types may not become smaller.</p>
            <label>Encrypt this file?<select value={encrypt ? "yes" : "no"} onChange={e => { setEncrypt(e.target.value === "yes"); setPassword(""); setConfirmation(""); }}><option value="no">No — keep the copy readable</option><option value="yes">Yes — protect the copy with a password</option></select></label>
            {encrypt && <><label>Encryption password<input type="password" autoComplete="new-password" value={password} maxLength={256} onChange={e => setPassword(e.target.value)} /></label><label>Confirm password<input type="password" autoComplete="new-password" value={confirmation} maxLength={256} onChange={e => setConfirmation(e.target.value)} /></label><p>Use 12–256 characters. Keep the password safely; it is not saved and cannot be recovered.</p></>}
            <button disabled={!ready} onClick={() => void run(async () => {
              if (encrypt && (password.length < 12 || password !== confirmation)) throw new Error("Use at least 12 characters and matching passwords.");
              await request(`/${selected.id}/prepare`, json({ compress, encrypt, password }));
              setPassword(""); setConfirmation(""); await refresh(); setNotice("Prepared copy saved locally. The original is unchanged. Nothing was sent to base.");
            })}>Create prepared copy</button>
          </fieldset>
        </div>
      </div>
      {!!selected.copies.length && <><h3>Prepared copies</h3><p>Download a copy as stored, or restore its original contents. Restoring downloads a file without saving another copy on the server.</p>
        {selected.copies.some(copy => copy.encrypted) && <label>Password to restore an encrypted copy<input type="password" autoComplete="off" value={unlock} maxLength={256} onChange={e => setUnlock(e.target.value)} /></label>}
        {selected.copies.map(copy => <div className="prepared-copy" key={copy.id}>
          <p><b>{copy.encrypted ? "Encrypted" : "Not encrypted"} · {copy.compressed ? "Compressed" : "Not compressed"}</b> · {size(copy.size)} · Stored locally</p><p className="storage-path">{copy.storage_path}</p>
          <a href={`/api/files/copies/${copy.id}/download`}>Download prepared copy</a>{" "}
          <button disabled={busy} onClick={() => void run(async () => {
            const response = await request(`/copies/${copy.id}/restore`, json({ password: unlock }));
            const url = URL.createObjectURL(await response.blob()); const link = document.createElement("a");
            link.href = url; link.download = selected.name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 10000);
            setUnlock(""); setNotice("Restored file downloaded.");
          })}>Restore and download</button>
        </div>)}</>}
    </section>}
  </section>;
}
