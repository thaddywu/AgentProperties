import { fileURLToPath } from "node:url";
import { loadReviewApplication } from "@rakazo/policy-translation/review";
import { expect, it, vi } from "vitest";
import { policyReviewHandler } from "./server";

const load = () =>
  loadReviewApplication(
    fileURLToPath(new URL("../../../../../../apps/labcluster-port", import.meta.url)),
  );

it("provides the offline reference without requiring a model and never substitutes it for a translation", async () => {
  const handler = policyReviewHandler(load);
  const result = await handler({ operation: "load" });
  expect(result.modelAvailable).toBe(false);
  expect(result.review.origin).toBe("reference");
  await expect(
    handler({ operation: "translate", policyText: "P1. Students read their own jobs." }),
  ).rejects.toThrow("Connect a model");
});

it("rejects client-selected files, bindings and oversized text before accessing application data", async () => {
  const loader = vi.fn(load);
  const handler = policyReviewHandler(loader, vi.fn());
  for (const body of [
    null,
    { operation: "load", directory: "elsewhere" },
    { operation: "translate", policyText: "P1. Test.", binding: {} },
    { operation: "translate", policyText: "x".repeat(24001) },
  ])
    await expect(handler(body)).rejects.toThrow();
  expect(loader).not.toHaveBeenCalled();
});

it("serializes model work, sanitizes provider failures and releases the lock after failure", async () => {
  const app = await load();
  let fail!: (e: Error) => void;
  const generate = vi.fn(
    () =>
      new Promise<string>((_resolve, reject) => {
        fail = reject;
      }),
  );
  const handler = policyReviewHandler(async () => app, generate);
  const body = {
    operation: "translate",
    policyText: app.documents.find((d) => d.path === "policy.md")!.content,
  };
  const first = handler(body);
  const rejection = expect(first).rejects.toThrow("The model could not finish");
  await vi.waitFor(() => expect(generate).toHaveBeenCalledOnce());
  await expect(handler(body)).rejects.toThrow("already running");
  fail(new Error("Provider failure containing a private connection value"));
  await rejection;
  generate.mockRejectedValueOnce(new Error("another provider failure"));
  await expect(handler(body)).rejects.toThrow("The model could not finish");
});
