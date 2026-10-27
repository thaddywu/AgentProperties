import { afterEach, expect, it, vi } from "vitest";
import { loadState } from "./client";

afterEach(() => vi.unstubAllGlobals());

it("shares repeated state loads while pending and refreshes after completion", async () => {
  let respond!: (response: Response) => void;
  const fetch = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        respond = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetch);
  const first = loadState({});
  expect(loadState({})).toBe(first);
  expect(fetch).toHaveBeenCalledTimes(1);
  respond(new Response(JSON.stringify({ result: { version: 1 } }), { status: 200 }));
  await first;
  const next = loadState({});
  expect(fetch).toHaveBeenCalledTimes(2);
  respond(new Response(JSON.stringify({ result: { version: 2 } }), { status: 200 }));
  expect(await next).toEqual({ version: 2 });
});
