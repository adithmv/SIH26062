import { network } from "./transport";
import { configureLink, linkSettings } from "./connectivity";
import type { Profile } from "./connectivity";
import type { MissionDetail } from "./api";
import { useEffect, useState } from "react";
import { liveQuery } from "dexie";
import {
  db,
  prepareOffline,
  sendPending,
  STORE_ERROR,
  reviewConflict,
  resolveConflict,
} from "./localStore";
import { useDeliveries } from "./useDeliveries";
import { utc } from "./api";

export function LocalReports({ missionId }: { missionId: string }) {
  const { items, error } = useDeliveries(missionId);
  const outstanding = items.filter((item) => item.state !== "acknowledged");
  if (!outstanding.length && !error) return null;
  return (
    <section className="local-reports">
      <h3>Reports saved on this device</h3>
      <p className="muted">
        Not yet confirmed by the server. These reports do not clear the server's
        contact alerts.
      </p>
      {error && <p role="alert">{error}</p>}
      {outstanding.map((item) => (
        <article key={item.id} className="check-in">
          <span className={"status delivery-" + item.state}>{item.state}</span>
          <p>
            {item.kind === "check-ins"
              ? item.body.note
              : "Position: " +
                item.body.latitude +
                "°, " +
                item.body.longitude +
                "°"}
          </p>
          <small>
            {utc(item.body.observed_at)} · {item.body.source}
          </small>
          {item.error && <p className="form-error">{item.error}</p>}
        </article>
      ))}
    </section>
  );
}
export default function OfflinePanel({ onRefresh }: { onRefresh: () => void }) {
  const { items, error: dbError } = useDeliveries();
  const [cachedPaths, setCachedPaths] = useState<string[]>([]);
  const [online, setOnline] = useState(navigator.onLine);
  const [shell, setShell] = useState(false);
  const [prepared, setPrepared] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState(linkSettings);
  const [review, setReview] = useState<{
    id: string;
    mission: MissionDetail;
  } | null>(null);
  useEffect(() => {
    const update = () => setLink(linkSettings());
    const deliver = () => {
      void sendPending(undefined, true).catch(() => setError(STORE_ERROR));
    };
    const timer = setInterval(deliver, 5000);
    window.addEventListener("polaris-link", update);
    window.addEventListener("storage", update);
    window.addEventListener("online", deliver);
    deliver();
    return () => {
      clearInterval(timer);
      window.removeEventListener("polaris-link", update);
      window.removeEventListener("storage", update);
      window.removeEventListener("online", deliver);
    };
  }, []);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    const read = (event: Event) => {
      const { path, cached } = (
        event as CustomEvent<{ path: string; cached: boolean }>
      ).detail;
      setCachedPaths((previous) =>
        cached
          ? [...new Set([...previous, path])]
          : previous.filter((p) => p !== path),
      );
    };
    window.addEventListener("polaris-read", read);
    const storage = (event: Event) =>
      setError((event as CustomEvent<string>).detail);
    const subscription = liveQuery(() =>
      db.settings.get("preparedAt"),
    ).subscribe({
      next: (row) => setPrepared(row?.value ?? ""),
      error: () => setError(STORE_ERROR),
    });
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    window.addEventListener("polaris-storage-error", storage);
    if ("serviceWorker" in navigator)
      void navigator.serviceWorker.ready.then(() => setShell(true));
    return () => {
      window.removeEventListener("polaris-read", read);
      subscription.unsubscribe();
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
      window.removeEventListener("polaris-storage-error", storage);
    };
  }, []);
  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      onRefresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to finish.");
    } finally {
      setBusy(false);
    }
  }
  const outstanding = items.filter((i) => i.state !== "acknowledged");
  return (
    <section
      className="offline-panel"
      aria-label="Offline storage and delivery"
    >
      <div className="section-heading">
        <div>
          <h2>
            {online
              ? "Offline storage & sync"
              : "Offline · working from this device"}
          </h2>
          <p className="muted">
            {shell ? "App shell cached" : "App shell not yet cached"} ·{" "}
            {prepared
              ? "Mission pack saved " + utc(prepared)
              : "Save a mission pack before disconnecting."}
          </p>
        </div>
        <span className="status">{outstanding.length} undelivered</span>
      </div>
      {cachedPaths.length > 0 && (
        <p role="status" className="cached-warning">
          Showing saved records. Server status may be out of date.
        </p>
      )}
      <details className="connection-settings">
        <summary>Connection settings</summary>
      <div className="actions">
        <label>
          Connection profile{" "}
          <select
            aria-label="Connection profile"
            value={link.profile}
            onChange={(e) =>
              configureLink(e.target.value as Profile, link.failures)
            }
          >
            <option value="broadband">Broadband</option>
            <option value="constrained">Constrained</option>
            <option value="offline">Offline</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={link.failures}
            onChange={(e) => configureLink(link.profile, e.target.checked)}
          />{" "}
          Simulate request failures
        </label>
        <button
          disabled={busy}
          onClick={() =>
            run(async () => {
              await network("health");
              setError("Server is reachable using the selected profile.");
            })
          }
        >
          Check server connection
        </button>
      </div>
      <p className="muted">
        Constrained mode: 800 ms delay, 2,048 outgoing bytes per minute.
        Automatic sync checks every five seconds while this page is open.
      </p>
      </details>
      {review && (
        <section
          className="local-reports"
          aria-label="Review conflicting report"
        >
          <h3>Review server version {review.mission.version}</h3>
          <p>
            {review.mission.code}: {review.mission.status}. Last contact:{" "}
            {review.mission.last_contact_at
              ? utc(review.mission.last_contact_at)
              : "None"}
            . Latest check-in: {review.mission.check_ins[0]?.note ?? "None"}.
          </p>
          <p>
            Your original report remains saved. Append it using this reviewed
            version; its original observation time will be preserved. A further
            server change will require another review.
          </p>
          <button
            disabled={busy || review.mission.status !== "in_field"}
            onClick={() =>
              run(async () => {
                await resolveConflict(review.id, review.mission.version);
                setReview(null);
              })
            }
          >
            Append report to reviewed version
          </button>
          <button onClick={() => setReview(null)}>Cancel review</button>
        </section>
      )}
      <div className="actions">
        <button disabled={busy || !online} onClick={() => run(prepareOffline)}>
          Save mission pack
        </button>
        <button
          disabled={busy || !online || !outstanding.length}
          onClick={() => run(() => sendPending())}
        >
          Send pending reports
        </button>
        <button
          onClick={() =>
            run(async () => {
              const kept = await navigator.storage?.persist?.();
              if (!kept)
                throw new Error(
                  "Persistent storage was not granted. Data remains stored but the browser may remove it under storage pressure.",
                );
            })
          }
        >
          Keep data on device
        </button>
      </div>
      {(error || dbError) && (
        <p role="alert" className="form-error">
          {error || dbError}
        </p>
      )}
      {items.length > 0 && (
        <details>
          <summary>Delivery history ({items.length})</summary>
          <div className="delivery-list">
            {items.map((item) => (
              <article className="delivery-row" key={item.id}>
                <span>
                  {item.missionCode} ·{" "}
                  {item.kind === "check-ins" ? "Check-in" : "Position"}
                </span>
                <span className={"status delivery-" + item.state}>
                  {item.state}
                </span>
                <small>
                  {item.acknowledgedAt
                    ? "Acknowledged " + utc(item.acknowledgedAt)
                    : "Saved locally " + utc(item.createdAt)}
                </small>
                {item.error && <p>{item.error}</p>}
                {item.resolution && <small>{item.resolution}</small>}
                {item.conflict && (
                  <button
                    disabled={busy || !online}
                    onClick={() =>
                      run(async () =>
                        setReview({
                          id: item.id,
                          mission: await reviewConflict(item.id),
                        }),
                      )
                    }
                  >
                    Review server conflict
                  </button>
                )}
                {item.state === "failed" && (
                  <button
                    disabled={busy || !online}
                    onClick={() => run(() => sendPending(item.id))}
                  >
                    Retry unchanged report
                  </button>
                )}
              </article>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
