import { useEffect, useRef, useState } from "react";

type Copy = { available: boolean; created_at: string; id: string; size: number; compressed: boolean; encrypted: boolean; storage_path: string };
type StoredFile = { available: boolean; created_at: string; id: string; name: string; size: number; importance: string; confidentiality: string; storage_path: string; status: string; copies: Copy[] };
type Listing = { folders: Record<"originals" | "prepared", string>; storage_root: string; max_bytes: number; files: StoredFile[] };
const size = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KiB` : `${(bytes / 1024 / 1024).toFixed(1)} MiB`;
const date = (value: string) => new Date(/Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : value + "Z").toLocaleString();
async function request(path: string, init?: RequestInit) {
  let response: Response;
  try {
    response = await fetch(`/api/files${path}`, { ...init, cache: "no-store" });
  } catch {
    throw new Error(init?.method && init.method !== "GET"
      ? "Connection interrupted. Refresh the file list before retrying; the operation may already have finished."
      : "Cannot reach file storage. Check that the backend is running.");
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : "Could not complete the file operation.");
  }
  return response;
}
const json = (body: unknown, method = "POST") => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export default function DataManagement({ revision }: { revision: number }) {
  const operation = useRef(false);
  const editor = useRef<HTMLElement>(null);
  const requestVersion = useRef(0);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("newest");
  const [progress, setProgress] = useState("");
  const [loadError, setLoadError] = useState("");
  const [listing, setListing] = useState<Listing | null>(null);
  const [selected, setSelected] = useState<StoredFile | null>(null);
  const [folder, setFolder] = useState<"originals" | "prepared">("originals");
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
  function accept(data: Listing) {
    setListing(data);
    setLoadError("");
    setSelected(current => current ? data.files.find(file => file.id === current.id) ?? null : null);
  }
  async function refresh() {
    const version = ++requestVersion.current;
    try {
      const data: Listing = await (await request("")).json();
      if (version === requestVersion.current) accept(data);
    } catch (e) {
      if (version === requestVersion.current) setLoadError(e instanceof Error ? e.message : "Storage unavailable.");
      throw e;
    }
  }
  useEffect(() => {
    if (operation.current) return;
    let active = true;
    const version = ++requestVersion.current;
    request("").then(response => response.json()).then((data: Listing) => {
      if (active && version === requestVersion.current) accept(data);
    }).catch(e => { if (active && version === requestVersion.current) setLoadError(e.message); });
    return () => { active = false; };
  }, [revision]);
  async function run(action: () => Promise<void>) {
    if (operation.current) return;
    operation.current = true;
    ++requestVersion.current;
    setBusy(true); setError(""); setNotice("");
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : "File operation failed."); }
    finally { operation.current = false; setBusy(false); setProgress(""); }
  }
  function canLeaveEditor() {
    return !dirty || window.confirm("Discard the unsaved data-level changes?");
  }
  function applyFile(file: StoredFile) {
    setListing(current => current ? { ...current, files: current.files.map(row => row.id === file.id ? file : row) } : current);
    setSelected(file);
  }
  async function download(path: string, name: string, options?: RequestInit) {
    const response = await request(path, options);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url; link.download = name;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }
  function edit(file: StoredFile) {
    if (selected?.id === file.id) { editor.current?.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    if (!canLeaveEditor()) return;
    setSelected(file); setImportance(file.importance); setConfidentiality(file.confidentiality);
    setReady(false); setCompress(true); setEncrypt(false); setPassword(""); setConfirmation(""); setUnlock(""); setNotice(""); setError("");
  }
  useEffect(() => {
    if (selected?.id) editor.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [selected?.id]);
  async function upload(files: File[]) {
    if (!files.length) return;
    await run(async () => {
      if (!listing || loadError) throw new Error("Reconnect to storage before uploading.");
      setFolder("originals"); setSearch("");
      let stored = 0;
      const failures: string[] = [];
      for (const [index, file] of files.entries()) {
        setProgress(`Uploading ${index + 1} of ${files.length}: ${file.name}`);
        try {
          if (!file.size) throw new Error("Empty files cannot be uploaded.");
          if (file.size > listing.max_bytes) throw new Error("Maximum file size is 20 MiB.");
          await request(`?name=${encodeURIComponent(file.name)}`, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
          stored++;
        } catch (e) { failures.push(`${file.name}: ${e instanceof Error ? e.message : "Upload failed."}`); }
      }
      setNotice(stored === 1 && files.length === 1 ? "File stored locally. Its location is shown below." : `${stored} of ${files.length} files stored locally.`);
      if (failures.length) setError(failures.join(" "));
      await refresh();
    });
  }
  const dirty = !!selected && (importance !== selected.importance || confidentiality !== selected.confidentiality);
  const localFiles = (listing?.files ?? []).filter(file => file.name.toLowerCase().includes(search.toLowerCase()));
  const ordered = <T extends { name: string; size: number; created_at: string }>(items: T[]) => [...items].sort((a, b) => sort === "name" ? a.name.localeCompare(b.name) : sort === "size" ? b.size - a.size : new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  const originals = ordered(localFiles);
  const copies = ordered((listing?.files ?? []).flatMap(file => file.copies.map(copy => ({ ...copy, file, name: file.name + (copy.compressed ? ".gz" : "") + (copy.encrypted ? ".pemenc" : "") }))).filter(copy => copy.name.toLowerCase().includes(search.toLowerCase())));
  const visibleCount = folder === "originals" ? originals.length : copies.length;
  const totalBytes = (listing?.files ?? []).reduce((sum, file) => sum + (file.available ? file.size : 0) + file.copies.reduce((n, copy) => n + (copy.available ? copy.size : 0), 0), 0);
  return <section className="data-management" aria-label="File storage">
    <p>Browse files on this device on the left. The other device’s files will appear on the right when a connection is available.</p>
    {loadError && <div role="alert" className="form-error">Storage unavailable. {listing ? "Previously loaded files may be out of date." : "Check that the backend is running."} <button disabled={busy} onClick={() => void run(refresh)}>Retry storage</button></div>}
    {error && <p role="alert" className="form-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {busy && <p role="status">{progress || "Working… Please keep this page open."}</p>}
    <div className="file-manager">
      <section className="file-pane" aria-label="This device">
        <header className="file-pane-heading"><h2>This device</h2><span>Local storage</span></header>
        <div className="file-address"><strong>Folder</strong><span className="storage-path">{listing ? listing.folders[folder] : loadError ? "Storage unavailable" : "Loading storage location…"}</span></div>
        <div className="file-toolbar" role="group" aria-label="Local folders">
          <button aria-pressed={folder === "originals"} onClick={() => setFolder("originals")}>Originals</button>
          <button aria-pressed={folder === "prepared"} onClick={() => setFolder("prepared")}>Prepared copies</button>
        </div>
        <div className="file-search"><label>Find a file<input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name" /></label><label>Sort files<select value={sort} onChange={e => setSort(e.target.value)}><option value="newest">Newest first</option><option value="name">Name</option><option value="size">Largest first</option></select></label></div>
        <div className="file-pane-body">
          <div className="table-wrap"><table><thead><tr><th>Name</th><th>Size</th><th>{folder === "originals" ? "Data level" : "Protection"}</th><th>Actions</th></tr></thead><tbody>
            {folder === "originals" && originals.map(file => <tr key={file.id} className={selected?.id === file.id ? "file-selected" : ""}>
              <td><button className="file-name" disabled={busy} onClick={() => edit(file)}>{file.name}</button><small>{file.available ? date(file.created_at) : "File missing from storage"}</small></td>
              <td>{size(file.size)}</td><td>{file.importance} / {file.confidentiality}</td>
              <td><button disabled={busy} onClick={() => edit(file)}>Edit data level</button><br />{file.available && <button className="file-link" disabled={busy} onClick={() => void run(() => download(`/${file.id}/download`, file.name))}>Download original</button>}</td>
            </tr>)}
            {folder === "prepared" && copies.map(copy => <tr key={copy.id}>
              <td><button className="file-name" disabled={busy} onClick={() => edit(copy.file)}>{copy.name}</button><small>{copy.available ? date(copy.created_at) : "Copy missing from storage"}</small></td>
              <td>{size(copy.size)}</td><td>{copy.encrypted ? "Encrypted" : "Not encrypted"}<br />{copy.compressed ? "Compressed" : "Not compressed"}</td>
              <td>{copy.available && <button className="file-link" disabled={busy} onClick={() => void run(() => download(`/copies/${copy.id}/download`, copy.name))}>Download copy</button>}<br /><button disabled={busy} onClick={() => edit(copy.file)}>File details</button></td>
            </tr>)}
          </tbody></table></div>
          {!listing ? <p className="file-empty">{loadError ? "Storage unavailable. Use Retry storage above." : "Loading files…"}</p> : visibleCount === 0 && <p className="file-empty">{search ? "No files match your search." : folder === "originals" ? "This folder is empty. Add a file from your device below." : "No prepared copies yet. Select an original file to compress or encrypt it."}</p>}
        </div>
        <div className="file-pane-footer">{listing ? visibleCount : "—"} {visibleCount === 1 ? "file" : "files"}{search ? " matching" : ""} · {size(totalBytes)} stored across both folders{loadError ? " · May be out of date" : ""}</div>
        <div className="file-upload" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy && listing && !loadError) void upload(Array.from(e.dataTransfer.files)); }}><label>Add a file <input type="file" multiple disabled={busy || !listing || !!loadError} onChange={e => { void upload(Array.from(e.target.files ?? [])); e.target.value = ""; }} /></label><small>Choose or drop one or more files here. Up to 20 MiB each. Same-name files are kept separately. This shows the backend's storage, not your entire disk.</small></div>
      </section>
      <section className="file-pane" aria-label="Other device / Base">
        <header className="file-pane-heading"><h2>Other device / Base</h2><span>Not connected</span></header>
        <div className="file-address"><strong>Folder</strong><span>No remote folder available</span></div>
        <div className="file-toolbar"><span>Remote files</span></div>
        <div className="file-pane-body">
          <div className="table-wrap"><table><thead><tr><th>Name</th><th>Size</th><th>Status</th></tr></thead><tbody /></table></div>
          <div className="file-empty"><strong>No device connected</strong><p>Remote browsing and file transfer are not implemented yet.</p></div>
        </div>
        <div className="file-pane-footer">Remote file count unavailable</div>
        <div className="file-upload"><p>Preparing a local copy does not send it to the other device.</p></div>
      </section>
    </div>
    <div className="transfer-status" aria-label="File transfer status"><strong>Transfers</strong><span>Not available yet · No files sent to base</span></div>
    {selected && <section ref={editor} className="panel file-editor" aria-label="Edit data level">
      <div className="page-heading"><h2>Edit data level — {selected.name}</h2><button disabled={busy} onClick={() => { if (!canLeaveEditor()) return; setSelected(null); setPassword(""); setConfirmation(""); setUnlock(""); }}>Close</button></div>
      {(error || busy) && <p className={error ? "form-error" : "muted"}>{error || "Working…"}</p>}
      <div className="file-split">
        <div><h3>1. Select the original</h3>
          <div className="file-drop" draggable={!busy && selected.available} onDragStart={e => e.dataTransfer.setData("text/plain", selected.id)}>
            <strong>{selected.name}</strong><p>{size(selected.size)} · Added {date(selected.created_at)}</p>{!selected.available && <p role="alert">Original missing from storage. Existing prepared copies can still be restored.</p>}<p className="storage-path">{selected.storage_path}</p>
            <p>Drag this file to the preparation area, or use the button.</p>
            <button disabled={busy || !selected.available} onClick={() => setReady(true)}>Use this file</button>
          </div>
          <p>The original stays unchanged and unencrypted. A confidential label alone does not protect its contents.</p>
        </div>
        <div><h3>2. Set level and prepare a copy</h3>
          <fieldset disabled={busy}>
            <label>Importance<select value={importance} onChange={e => setImportance(e.target.value)}><option value="normal">Normal</option><option value="important">Important</option><option value="critical">Critical</option></select></label>
            <label>Confidentiality<select value={confidentiality} onChange={e => setConfidentiality(e.target.value)}><option value="normal">Normal</option><option value="confidential">Confidential</option></select></label>
            <button onClick={() => void run(async () => { const updated: StoredFile = await (await request(`/${selected.id}`, json({ importance, confidentiality }, "PATCH"))).json(); applyFile(updated); setNotice("Data level saved. File contents are unchanged."); })}>Save data level</button>
            <div className="file-drop" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy && selected.available && e.dataTransfer.getData("text/plain") === selected.id) setReady(true); }}>
              {ready ? `Selected: ${selected.name}` : "Preparation area — drop the original here or choose Use this file."}
            </div>
            <label className="file-check"><input type="checkbox" checked={compress} onChange={e => setCompress(e.target.checked)} /> Compress the copy</label>
            <p>Compression runs first. Some file types may not become smaller.</p>
            <label>Encrypt this file?<select value={encrypt ? "yes" : "no"} onChange={e => { setEncrypt(e.target.value === "yes"); setPassword(""); setConfirmation(""); }}><option value="no">No — keep the copy readable</option><option value="yes">Yes — protect the copy with a password</option></select></label>
            {encrypt && <><label>Encryption password<input type="password" autoComplete="new-password" value={password} maxLength={256} onChange={e => setPassword(e.target.value)} /></label><label>Confirm password<input type="password" autoComplete="new-password" value={confirmation} maxLength={256} onChange={e => setConfirmation(e.target.value)} /></label><p>Use 12–256 characters. Keep the password safely; it is not saved and cannot be recovered.</p></>}
            <p>{dirty ? "You have unsaved data-level changes. Save the data level before creating a copy." : "Data level saved."}</p>
            <button disabled={!ready || dirty || !selected.available} onClick={() => void run(async () => {
              if (encrypt && (Array.from(password).length < 12 || password !== confirmation)) throw new Error("Use at least 12 characters and matching passwords.");
              const updated: StoredFile = await (await request(`/${selected.id}/prepare`, json({ compress, encrypt, password: encrypt ? password : "" }))).json();
              applyFile(updated); setPassword(""); setConfirmation(""); setNotice("Prepared copy saved locally. The original is unchanged. Nothing was sent to base.");
            })}>Create prepared copy</button>
          </fieldset>
        </div>
      </div>
      {!!selected.copies.length && <><h3>Prepared copies</h3><p>Download a copy as stored, or restore its original contents. Restoring downloads a file without saving another copy on the server.</p>
        {selected.copies.some(copy => copy.encrypted) && <label>Password to restore an encrypted copy<input type="password" autoComplete="off" value={unlock} maxLength={256} onChange={e => setUnlock(e.target.value)} /></label>}
        {selected.copies.map(copy => <div className="prepared-copy" key={copy.id}>
          <p><b>{copy.encrypted ? "Encrypted" : "Not encrypted"} · {copy.compressed ? "Compressed" : "Not compressed"}</b> · {size(copy.size)} · {copy.available ? "Stored locally" : "Missing from storage"}</p><p>{copy.size < selected.size ? `${size(selected.size - copy.size)} smaller than the original` : copy.size > selected.size ? `${size(copy.size - selected.size)} larger than the original` : "Same size as the original"} · Created {date(copy.created_at)}</p><p className="storage-path">{copy.storage_path}</p>
          {copy.available && <button className="file-link" disabled={busy} onClick={() => void run(() => download(`/copies/${copy.id}/download`, selected.name + (copy.compressed ? ".gz" : "") + (copy.encrypted ? ".pemenc" : "")))}>Download prepared copy</button>}{" "}
          <button disabled={busy || !copy.available} onClick={() => void run(async () => {
            await download(`/copies/${copy.id}/restore`, selected.name, json({ password: copy.encrypted ? unlock : "" }));
            setUnlock(""); setNotice("Restored file download started.");
          })}>Restore and download</button>
        </div>)}</>}
    </section>}
  </section>;
}
