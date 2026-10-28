import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { PolicyBundle } from "@rakazo/policy-runtime/application";
import { readRuntimeBinding } from "@rakazo/policy-runtime/binding";
import { afterEach, expect, it, vi } from "vitest";
import { createDocumentService } from "../../apps/document-vault/src/service.js";
import { loadApplication } from "./application.js";
import { translateApplication } from "./application-translation.js";

const roots: string[] = [];
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});
async function setup() {
  const root = await mkdtemp(join(tmpdir(), "application-translation-"));
  roots.push(root);
  const app = new URL("../../apps/document-vault/", import.meta.url);
  return {
    output: join(root, "run"),
    documents: await loadApplication(app.pathname),
    binding: readRuntimeBinding(JSON.parse(await readFile(new URL("runtime.json", app), "utf8"))),
  };
}
const policies = [
  {
    id: "P1",
    datalog: 'Allow(R) :- Request(R, A, "read", D), Accessible(A, D).',
    notes: "Synthetic offline model output.",
  },
  { id: "P2", datalog: 'Deny(R, "suspended") :- Request(R, A, X, D), Suspended(A).', notes: "" },
  {
    id: "P3",
    datalog:
      'Accessible(A, D) :- Actor(A), Public(D), not Suspended(A).\nAccessible(A, D) :- Actor(A), Confidential(D), Reader(A, D), Role(A, "reviewer"), not Suspended(A).',
    notes: "Successful-read instrumentation remains the app's responsibility.",
  },
];

it("runs app documents -> one translation -> validated artifact -> real gated app -> query and why", async () => {
  const options = await setup();
  const generate = vi.fn(async (prompt: string) => {
    expect(prompt).not.toContain("Nova");
    expect(prompt).not.toContain("public-read"); // Held-out binding acceptance cases are not prompt examples.
    expect(prompt).not.toContain('"tests"');
    return JSON.stringify({ policies });
  });
  const result = await translateApplication({ ...options, generate });
  expect(result.status).toBe("validated_policy_bundle");
  expect(generate).toHaveBeenCalledTimes(1);
  const artifact = JSON.parse(
    await readFile(join(options.output, "policy-bundle.json"), "utf8"),
  ) as PolicyBundle;
  const service = createDocumentService(
    options.binding,
    artifact,
    [
      { predicate: "Actor", args: ["visitor"] },
      { predicate: "Public", args: ["guide"] },
      { predicate: "Confidential", args: ["draft"] },
    ],
    { guide: "guide body", draft: "synthetic secret body" },
  );
  const denied = await service.read("visitor", "draft");
  expect(denied.allowed).toBe(false);
  expect(denied).not.toHaveProperty("value");
  expect(service.payloadReads).toBe(0);
  expect((await service.read("visitor", "guide")).allowed).toBe(true);
  expect(service.payloadReads).toBe(1);
  expect(service.session.query("?- Read(A, D).").rows).toEqual([["visitor", "guide"]]);
  expect(
    service.session.why({ predicate: "Accessible", args: ["visitor", "guide"] })?.rule,
  ).toBeTruthy();
});

it("does not emit an executable artifact for weakened or incomplete policies; raw output survives", async () => {
  for (const outputPolicies of [
    policies.map((policy) => ({
      ...policy,
      datalog: policy.datalog.replace(', Role(A, "reviewer")', ""),
    })),
    policies.map((policy) => ({ ...policy, datalog: policy.id === "P2" ? "" : policy.datalog })),
  ]) {
    const options = await setup();
    const raw = JSON.stringify({ policies: outputPolicies });
    const result = await translateApplication({ ...options, generate: async () => raw });
    expect(result.status).not.toBe("validated_policy_bundle");
    await expect(readFile(join(options.output, "policy-bundle.json"))).rejects.toThrow();
    expect(await readFile(join(options.output, "raw-response.txt"), "utf8")).toBe(raw);
  }
});
