export type Profile = "broadband" | "constrained" | "offline";
export class LinkDeferred extends Error {}
const key = "polaris-link";
export function linkSettings(): { profile: Profile; failures: boolean } {
  try {
    return {
      profile: "broadband",
      failures: false,
      ...JSON.parse(localStorage.getItem(key) || "{}"),
    };
  } catch {
    return { profile: "broadband", failures: false };
  }
}
export function configureLink(profile: Profile, failures: boolean) {
  localStorage.setItem(key, JSON.stringify({ profile, failures }));
  window.dispatchEvent(new Event("polaris-link"));
}
export async function beforeRequest(body: unknown, signal: AbortSignal) {
  const { profile, failures } = linkSettings();
  if (profile === "offline" || !navigator.onLine)
    throw new LinkDeferred(
      "Offline profile: saved requests remain on this device.",
    );
  if (profile === "constrained") {
    await new Promise<void>((resolve, reject) => {
      const abort = () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      };
      const timer = setTimeout(() => {
        signal.removeEventListener("abort", abort);
        resolve();
      }, 800);
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) abort();
    });
  }
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  if (linkSettings().profile === "offline")
    throw new LinkDeferred("Offline profile enabled.");
  if (failures)
    throw new Error(
      "Simulated request failure. Disable failure simulation to reconnect.",
    );
  // Budget is UTF-8 outgoing JSON payload, not physical link traffic or response bytes.
  if (body && profile === "constrained") {
    await navigator.locks.request("polaris-byte-budget", async () => {
      const now = Date.now();
      let meter = JSON.parse(
        localStorage.getItem("polaris-byte-meter") || "null",
      ) || { start: now, bytes: 0 };
      if (now - meter.start >= 60000) meter = { start: now, bytes: 0 };
      const bytes = new TextEncoder().encode(JSON.stringify(body)).byteLength;
      if (meter.bytes + bytes > 2048)
        throw new LinkDeferred(
          "Constrained payload budget exhausted; waiting for the next minute.",
        );
      localStorage.setItem(
        "polaris-byte-meter",
        JSON.stringify({ ...meter, bytes: meter.bytes + bytes }),
      );
    });
  }
}
