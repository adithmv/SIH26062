import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import App from "./App";
import { setBaseMode, setBaseUser } from "./baseMode";

type Session = { mode: "local" | "base"; user: { username: string; role: string } | null };
export default function BaseAccess() {
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const loaded = useRef(false);
  const refresh = useCallback(async () => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch("/api/auth/session", { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("Cannot check base access. Try again.");
      const value: Session = await response.json();
      if (import.meta.env.VITE_BASE_MODE === "true" && value.mode !== "base") throw new Error("This dashboard requires a base server. Check server configuration.");
      setBaseMode(value.mode === "base");
      setBaseUser(value.user);
      setSession(value);
      loaded.current = true;
      setError("");
    } catch (e) {
      // Only the development/field build supports offline startup. The deployed base build fails closed.
      if (import.meta.env.VITE_BASE_MODE !== "true" && !loaded.current) {
        setBaseMode(false); setSession({ mode: "local", user: null });
      } else setError(e instanceof Error ? e.message : "Cannot reach the base server.");
    } finally { clearTimeout(timeout); }
  }, []);
  useEffect(() => {
    const start = setTimeout(() => { void refresh(); }, 0);
    const expired = () => setSession({ mode: "base", user: null });
    window.addEventListener("base-session-expired", expired);
    return () => { clearTimeout(start); window.removeEventListener("base-session-expired", expired); };
  }, [refresh]);
  useEffect(() => {
    if (session?.mode !== "base" || !session.user?.username) return;
    const timer = setInterval(() => { void refresh(); }, 60000);
    return () => clearInterval(timer);
  }, [session?.mode, session?.user?.username, refresh]);
  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
      const value = await response.json();
      if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : "Sign-in failed.");
      setPassword(""); await refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Cannot sign in."); }
    finally { setBusy(false); }
  }
  async function logout() {
    setBusy(true);
    try {
      const response = await fetch("/api/auth/logout", { method: "POST" });
      if (!response.ok && response.status !== 401) throw new Error("Cannot sign out. Retry when connected.");
      setSession({ mode: "base", user: null });
    } catch (e) { setError(e instanceof Error ? e.message : "Cannot sign out."); }
    finally { setBusy(false); }
  }
  if (!session) return <main className="shell"><h1>Polar Expedition Manager</h1><p>{error || "Checking server access…"}</p>{error && <button onClick={refresh}>Retry</button>}</main>;
  if (session.mode === "local") return <App />;
  if (!session.user) return <main className="shell"><h1>Base station sign-in</h1><p>Use the account created by your station administrator.</p><form onSubmit={login} className="action-form"><label>Username<input autoComplete="username" required maxLength={80} value={username} onChange={e => setUsername(e.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={e => setPassword(e.target.value)} /></label>{error && <p role="alert">{error}</p>}<button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form></main>;
  return <><aside className="base-session"><span>Base station · {session.user.username} · {session.user.role}{session.user.role === "viewer" ? " (read only)" : ""}</span><button onClick={logout} disabled={busy}>Sign out</button>{error && <p role="alert">{error}</p>}</aside><App key={session.user.username} /></>;
}
