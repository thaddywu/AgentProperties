import type { Request } from "@rakazo/core/policy/reasoning/service";
export async function request<T>(body: Request): Promise<T> {
  const response = await fetch("/nova-api", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? "Request failed");
  return data.result as T;
}
