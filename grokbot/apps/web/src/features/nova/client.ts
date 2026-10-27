import type { NovaView, Request, Selection } from "@rakazo/nova/service";

let pendingState: { key: string; promise: Promise<NovaView> } | undefined;

// StrictMode may repeat the same effect before the single-worker backend has answered.
export function loadState(selection: Selection): Promise<NovaView> {
  const key = JSON.stringify(selection);
  if (pendingState?.key === key) return pendingState.promise;
  const promise = request<NovaView>({ operation: "state", ...selection });
  pendingState = { key, promise };
  const clear = () => {
    if (pendingState?.promise === promise) pendingState = undefined;
  };
  void promise.then(clear, clear);
  return promise;
}

export async function request<T>(body: Request): Promise<T> {
  try {
    const response = await fetch("/nova-api", {
      method: "POST",
      signal: AbortSignal.timeout(25_000),
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? "Request failed");
    return data.result as T;
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError")
      throw new Error(
        "Request timed out. Check the port forward or run ./nova-demo.sh on the server, then refresh the page.",
      );
    throw error;
  }
}
