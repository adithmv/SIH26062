export class LinkDeferred extends Error {}
export async function beforeRequest(signal: AbortSignal) {
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  if (!navigator.onLine)
    throw new LinkDeferred("Offline: saved requests remain on this device.");
}
