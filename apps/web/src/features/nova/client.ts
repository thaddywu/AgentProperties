import type { Request } from "@rakazo/core/policy/reasoning/service";
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
