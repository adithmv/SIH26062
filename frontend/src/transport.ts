import { beforeRequest } from "./connectivity";
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
export async function network<T>(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal?.addEventListener("abort", abort, { once: true });
  if (signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 5000);
  try {
    await beforeRequest(body, controller.signal);
    const response = await fetch("/api/" + path, {
      method,
      signal: controller.signal,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail
                .map(
                  (e: { msg: string; loc: string[] }) =>
                    e.loc.slice(1).join(".") + ": " + e.msg,
                )
                .join("; ")
            : "Check that the API is running.";
      throw new ApiError(
        (method === "GET"
          ? "Unable to load data. "
          : "Not accepted by the server. ") + detail,
        response.status,
      );
    }
    return (await response.json()) as T;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
